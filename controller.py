"""Match Fritchii's SDL backend and refresh stale controller IDs before launch."""
import configparser
import ctypes as c
import json
import re
import subprocess
import time
from pathlib import Path
from core import external_dlls


def make_mapping(mapping, device_guid=None, port=0):
    parts = mapping.split(',')
    guid = bytearray.fromhex(device_guid or parts[0])
    guid[2:4] = b'\0\0'
    base = f'engine:sdl,port:{port},guid:{guid.hex()}'
    fields = dict(p.split(':', 1) for p in parts[2:] if ':' in p)

    def button(name):
        value = fields.get(name, '')
        if re.fullmatch(r'b\d+', value):
            return base + ',button:' + value[1:]
        if re.fullmatch(r'h\d+\.\d+', value):
            hat, direction = value[1:].split('.')
            directions = {'1': 'up', '2': 'right', '4': 'down', '8': 'left'}
            if direction in directions:
                return base + ',hat:' + hat + ',direction:' + directions[direction]
        axis = re.fullmatch(r'([+-]?)a(\d+)(~?)', value)
        if axis:
            return base + f',axis:{axis[2]},threshold:0.5,invert:' + ('-' if axis[1] == '-' else '+')
        return None

    names = {'a': 'b', 'b': 'a', 'x': 'y', 'y': 'x', 'lstick': 'leftstick',
             'rstick': 'rightstick', 'l': 'leftshoulder', 'r': 'rightshoulder',
             'zl': 'lefttrigger', 'zr': 'righttrigger', 'plus': 'start', 'minus': 'back',
             'dleft': 'dpleft', 'dup': 'dpup', 'dright': 'dpright', 'ddown': 'dpdown',
             'home': 'guide'}
    settings = {}
    for target, source in names.items():
        result = button(source)
        if result:
            settings['player_0_button_' + target] = result
    for target, x, y in [('lstick', 'leftx', 'lefty'), ('rstick', 'rightx', 'righty')]:
        mx = re.fullmatch(r'a(\d+)(~?)', fields.get(x, ''))
        my = re.fullmatch(r'a(\d+)(~?)', fields.get(y, ''))
        if mx and my:
            settings['player_0_' + target] = base + f',axis_x:{mx[1]},axis_y:{my[1]},deadzone:0.15,range:1.0,offset_x:0,offset_y:0,invert_x:' + ('-' if mx[2] else '+') + ',invert_y:' + ('-' if my[2] else '+')
    required = ['player_0_button_' + x for x in ('a', 'b', 'x', 'y', 'l', 'r', 'zl', 'zr', 'plus', 'minus')]
    required += ['player_0_lstick', 'player_0_rstick']
    if not all(key in settings for key in required):
        raise ValueError('The gamepad does not expose a complete standard mapping')
    return settings


def main(root=None):
    folder = Path(root) / "support" if root is not None else Path(__file__).resolve().parent
    marker = folder / 'controller-configured.json'
    ini = folder.parent / 'user/config/qt-config.ini'
    config = configparser.RawConfigParser(strict=False)
    config.optionxform = str
    config.read(ini, encoding='utf-8-sig')
    with external_dlls():
        running = subprocess.run(
            ['tasklist.exe', '/FI', 'IMAGENAME eq lichii.exe', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    if '"lichii.exe"' in running.stdout.lower():
        raise RuntimeError('Fritchii is running; controller settings were not changed')
    c.windll.kernel32.SetErrorMode(3)
    s = c.CDLL(str(folder / 'SDL3.dll'))
    s.SDL_SetHint.argtypes = [c.c_char_p, c.c_char_p]
    s.SDL_SetHint.restype = c.c_bool
    # These are the same backend hints set in Fritchii v5.5's SDLDriver constructor.
    raw = config.getboolean('Controls', 'enable_raw_input', fallback=False)
    hints = {b'SDL_JOYSTICK_RAWINPUT': b'1' if raw else b'0',
             b'SDL_JOYSTICK_HIDAPI_XBOX': b'0',
             b'SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS': b'1'}
    if config.getboolean('Controls', 'disable_wgi_xinput', fallback=False):
        hints[b'SDL_JOYSTICK_RAWINPUT_CORRELATE_XINPUT'] = b'0'
        hints[b'SDL_JOYSTICK_WGI'] = b'0'
    for key, value in hints.items():
        s.SDL_SetHint(key, value)

    class GUID(c.Structure):
        _fields_ = [('data', c.c_uint8 * 16)]

    s.SDL_Init.argtypes = [c.c_uint32]
    s.SDL_Init.restype = c.c_bool
    s.SDL_GetJoysticks.argtypes = [c.POINTER(c.c_int)]
    s.SDL_GetJoysticks.restype = c.POINTER(c.c_uint32)
    s.SDL_GetGamepadMappingForID.argtypes = [c.c_uint32]
    s.SDL_GetGamepadMappingForID.restype = c.c_void_p
    s.SDL_GetJoystickNameForID.argtypes = [c.c_uint32]
    s.SDL_GetJoystickNameForID.restype = c.c_char_p
    s.SDL_OpenGamepad.argtypes = [c.c_uint32]
    s.SDL_OpenGamepad.restype = c.c_void_p
    s.SDL_CloseGamepad.argtypes = [c.c_void_p]
    s.SDL_GetGamepadJoystick.argtypes = [c.c_void_p]
    s.SDL_GetGamepadJoystick.restype = c.c_void_p
    s.SDL_GetJoystickGUID.argtypes = [c.c_void_p]
    s.SDL_GetJoystickGUID.restype = GUID
    s.SDL_GetGamepadMapping.argtypes = [c.c_void_p]
    s.SDL_GetGamepadMapping.restype = c.c_void_p
    s.SDL_PumpEvents.argtypes = []
    s.SDL_free.argtypes = [c.c_void_p]
    if not s.SDL_Init(0x200 | 0x2000):
        raise RuntimeError('SDL could not enumerate controllers')
    devices = []
    try:
        # Metadata can settle after the first enumeration; require two matching snapshots.
        last_signature = None
        for attempt in range(10):
            s.SDL_PumpEvents()
            count = c.c_int()
            ids = s.SDL_GetJoysticks(c.byref(count))
            devices = []
            ports = {}
            try:
                for i in range(count.value):
                    probe = s.SDL_GetGamepadMappingForID(ids[i])
                    if not probe:
                        continue
                    s.SDL_free(probe)
                    gamepad = s.SDL_OpenGamepad(ids[i])
                    if not gamepad:
                        continue
                    try:
                        joystick = s.SDL_GetGamepadJoystick(gamepad)
                        guid = bytearray(s.SDL_GetJoystickGUID(joystick).data)
                        guid[2:4] = b'\0\0'
                        guid = guid.hex()
                        port = ports.get(guid, 0)
                        ports[guid] = port + 1
                        ptr = s.SDL_GetGamepadMapping(gamepad)
                        if ptr:
                            mapping = c.string_at(ptr).decode()
                            s.SDL_free(ptr)
                            devices.append({'name': s.SDL_GetJoystickNameForID(ids[i]).decode(),
                                            'mapping': mapping, 'guid': guid, 'port': port})
                    finally:
                        s.SDL_CloseGamepad(gamepad)
            finally:
                s.SDL_free(ids)
            signature = [(d['guid'], d['port'], d['mapping']) for d in devices]
            if devices and signature == last_signature:
                break
            last_signature = signature
            time.sleep(0.2)
    finally:
        s.SDL_Quit()
    if not devices:
        print('No gamepad connected; keyboard bindings retained. Connect it before the next launch.')
        return
    devices.sort(key=lambda item: 'xbox' not in item['name'].lower())
    device = devices[0]
    name, mapping = device['name'], device['mapping']
    settings = make_mapping(mapping, device['guid'], device['port'])
    # Preserve custom bindings while they refer to the detected device. Repair only stale IDs.
    expected_id = f"guid:{device['guid']}"
    current = [config.get('Controls', key, fallback='').strip('"') for key in settings]
    same_device = all(expected_id in value for value in current)
    connected = config.getboolean('Controls', 'player_0_connected', fallback=False)
    if same_device and connected:
        marker.write_text(json.dumps({'version': 2, 'name': name, 'guid': device['guid'],
                                      'port': device['port'], 'bindings': len(settings)}, indent=2))
        print('Verified current controller; existing bindings retained: ' + name)
        return
    if not config.has_section('Controls'):
        config.add_section('Controls')
    for key, value in settings.items():
        config.set('Controls', key, value)
        config.set('Controls', key + '\\default', 'false')
    for key, value in {'player_0_connected': 'true', 'player_0_type': '0'}.items():
        config.set('Controls', key, value)
        config.set('Controls', key + '\\default', 'false')
    backup = folder / 'qt-config-before-controller.ini'
    if not backup.exists():
        backup.write_bytes(ini.read_bytes())
    temporary = ini.with_suffix('.ini.controller-tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as output:
        config.write(output, space_around_delimiters=False)
    temporary.replace(ini)
    marker.write_text(json.dumps({'version': 2, 'name': name, 'guid': device['guid'],
                                  'port': device['port'], 'bindings': len(settings)}, indent=2))
    print('Configured gamepad: ' + name)


if __name__ == '__main__':
    main()
