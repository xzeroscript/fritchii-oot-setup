"""Per-user setup using publisher downloads and a locally supplied game."""
from __future__ import annotations

import configparser
import contextlib
import ctypes as c
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
import struct

VERSION = '0.1.1'
TITLE_ID = 0x0400486024DEC000


def resource(name: str) -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / name


def manifest() -> dict:
    return json.loads(resource('manifest.json').read_text(encoding='utf-8'))


def digest(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def validate_game(path: Path) -> dict:
    """Check bounded NUP metadata without unpacking or reading the game payload."""
    if path.suffix.lower() != '.nup' or not path.is_file():
        raise ValueError('Select your own Ocarina of Time .nup file.')
    with path.open('rb') as source:
        head = source.read(128)
        if len(head) != 128 or head[:4] != b'NUP\x01':
            raise ValueError('This is not a supported NUP game file.')
        offset, size = struct.unpack_from('<QQ', head, 8)
        stated_size = struct.unpack_from('<Q', head, 64)[0]
        if stated_size != path.stat().st_size or not 48 <= size <= 64 * 1024**2:
            raise ValueError('The NUP file size or metadata is invalid.')
        if offset < 128 or offset + size > stated_size:
            raise ValueError('The NUP metadata is outside the file.')
        source.seek(offset)
        toc = source.read(size)
    if hashlib.sha256(toc).digest() != head[24:56] or toc[:4] != b'TOC\x01':
        raise ValueError('The game metadata checksum failed. Recheck your own dump.')
    count = struct.unpack_from('<I', toc, 4)[0]
    if count == 0 or 48 + 64 * count > len(toc):
        raise ValueError('The game package table is invalid.')
    packages = [struct.unpack_from('<Q', toc, 48 + 64*i)[0] for i in range(count)]
    if not any(value in (TITLE_ID, TITLE_ID + 0x800) for value in packages):
        raise ValueError('This setup supports Ocarina of Time, title 0400486024DEC000.')
    return {'size': stated_size, 'packages': count}


def extract_zip(archive: Path, destination: Path, *, strip_top=False, select=None):
    """Reject traversal and archive symlinks before writing any member."""
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        entries = []
        for member in package.infolist():
            name = member.filename.replace('\\', '/')
            relative = PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or any(':' in p for p in relative.parts):
                raise ValueError('Unsafe archive member: ' + name)
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Archive links are not accepted.')
            if select is not None and name not in select:
                continue
            parts = relative.parts[1:] if strip_top else relative.parts
            if not parts:
                continue
            target = destination.joinpath(*parts)
            if not target.resolve().is_relative_to(destination):
                raise ValueError('Archive member escapes its destination.')
            entries.append((member, target))
        for member, target in entries:
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(member) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)


def fetch(asset: dict, cache: Path, status) -> Path:
    path = cache / asset['name']
    if path.is_file() and digest(path) == asset['sha256']:
        return path
    partial = path.with_suffix(path.suffix + '.partial')
    status('Downloading ' + asset['name'])
    request = urllib.request.Request(asset['url'], headers={'User-Agent': 'Fritchii-OOT-Setup/' + VERSION})
    with urllib.request.urlopen(request, timeout=90) as source, partial.open('wb') as output:
        total = int(source.headers.get('Content-Length', 0))
        copied = 0
        while block := source.read(1024**2):
            output.write(block)
            copied += len(block)
            if total:
                status(f"Downloading {asset['name']}: {copied*100//total}%")
    if digest(partial) != asset['sha256']:
        partial.unlink(missing_ok=True)
        raise ValueError('Publisher checksum mismatch for ' + asset['name'])
    partial.replace(path)
    return path


def gpu_devices() -> list[dict]:
    """Use Vulkan's actual adapter order, including laptops with two GPUs."""
    if os.name != 'nt':
        return []
    try:
        vk = c.WinDLL(str(Path(os.environ['WINDIR']) / 'System32/vulkan-1.dll'))
        class Application(c.Structure):
            _fields_ = [('type', c.c_uint32), ('next', c.c_void_p), ('name', c.c_char_p),
                        ('version', c.c_uint32), ('engine', c.c_char_p),
                        ('engine_version', c.c_uint32), ('api', c.c_uint32)]
        class Create(c.Structure):
            _fields_ = [('type', c.c_uint32), ('next', c.c_void_p), ('flags', c.c_uint32),
                        ('app', c.POINTER(Application)), ('layers', c.c_uint32),
                        ('layer_names', c.c_void_p), ('extensions', c.c_uint32), ('extension_names', c.c_void_p)]
        app = Application(0, None, b'Fritchii setup', 1, None, 0, 1 << 22)
        info = Create(1, None, 0, c.pointer(app), 0, None, 0, None)
        instance = c.c_void_p()
        vk.vkCreateInstance.argtypes = [c.POINTER(Create), c.c_void_p, c.POINTER(c.c_void_p)]
        vk.vkDestroyInstance.argtypes = [c.c_void_p, c.c_void_p]
        vk.vkEnumeratePhysicalDevices.argtypes = [c.c_void_p, c.POINTER(c.c_uint32), c.c_void_p]
        vk.vkGetPhysicalDeviceProperties.argtypes = [c.c_void_p, c.c_void_p]
        if vk.vkCreateInstance(c.byref(info), None, c.byref(instance)) != 0:
            return []
        try:
            count = c.c_uint32()
            vk.vkEnumeratePhysicalDevices(instance, c.byref(count), None)
            devices = (c.c_void_p * count.value)()
            vk.vkEnumeratePhysicalDevices(instance, c.byref(count), devices)
            result = []
            for i, device in enumerate(devices):
                properties = c.create_string_buffer(4096)
                vk.vkGetPhysicalDeviceProperties(device, properties)
                vendor, _, kind = struct.unpack_from('<III', properties.raw, 8)
                name = properties.raw[20:276].split(b'\0', 1)[0].decode(errors='replace')
                result.append({'index': i, 'name': name, 'vendor': vendor, 'discrete': kind == 2})
            return result
        finally:
            vk.vkDestroyInstance(instance, None)
    except (OSError, AttributeError):
        return []


def fresh_config(root: Path, gpu: dict, dlss: bool):
    path = root / 'user/config/qt-config.ini'
    if path.exists():
        return  # Reinstalling never overwrites player settings or saves.
    config = configparser.RawConfigParser()
    config.optionxform = str
    values = {
        'Core': {'use_speed_limit': 'true', 'speed_limit': '100'},
        'Renderer': {'backend': '1', 'vulkan_device': str(gpu.get('index', 0)),
                     'resolution_setup': '3', 'nvidia_dlss': str(dlss).lower(),
                     'nvidia_dlss_preset': '2', 'oot_30fps': 'false', 'oot_fps_asked': 'true'},
        'System': {'use_docked_mode': '1', 'current_user': '0'},
        'Controls': {'player_0_type': '0', 'player_0_connected': 'true'},
        'UI': {'firstStart': 'false', 'fullscreen': 'true', 'hide_mouse': 'false',
               'Paths\\gamedirs\\size': '1', 'Paths\\gamedirs\\1\\path': (root / 'games').as_posix(),
               'Paths\\gamedirs\\1\\deep_scan': 'false', 'Paths\\gamedirs\\1\\expanded': 'true'},
        'DisabledAddOns': {'size': '1', '1\\title_id': str(TITLE_ID),
                          '1\\disabled\\size': '1', '1\\disabled\\1\\d': 'Max Resolution (built-in)'},
    }
    for section, entries in values.items():
        config[section] = {}
        for key, value in entries.items():
            config[section][key] = value
            if not key.endswith('size'):
                config[section][key + '\\default'] = 'false'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='\n') as output:
        config.write(output, space_around_delimiters=False)


@contextlib.contextmanager
def external_dlls():
    """Do not let the frozen launcher's DLL directory leak into Fritchii or system tools."""
    frozen = os.name == 'nt' and hasattr(sys, '_MEIPASS')
    if frozen:
        c.windll.kernel32.SetDllDirectoryW(None)
    try:
        yield
    finally:
        if frozen:
            c.windll.kernel32.SetDllDirectoryW(str(sys._MEIPASS))


def shortcuts(root: Path):
    # Pass data through an environment variable, never interpolate it into shell code.
    env = dict(os.environ, FRITCHII_SETUP_ROOT=str(root))
    script = r'''$s=New-Object -ComObject WScript.Shell
$root=$env:FRITCHII_SETUP_ROOT
$desktop=[Environment]::GetFolderPath('Desktop')
foreach($entry in @(@('Ocarina of Time (Fritchii)','--play'),@('Fritchii','--library'))) {
 $link=$s.CreateShortcut((Join-Path $desktop ($entry[0]+'.lnk')))
 $link.TargetPath=Join-Path $root 'Fritchii Launcher.exe'
 $link.Arguments=$entry[1]
 $link.WorkingDirectory=$root
 $link.IconLocation=(Join-Path $root 'support/ocarina.ico')+',0'
 $link.Save()
}'''
    with external_dlls():
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                       env=env, creationflags=subprocess.CREATE_NO_WINDOW, check=True,
                       capture_output=True, text=True)


def install(root: Path, game: Path, executable: Path, status=print, *, cache=None, create_shortcuts=True):
    details = validate_game(game)
    root = root.resolve()
    if len(root.parts) < 3:
        raise ValueError('Choose a dedicated installation folder, not a drive root.')
    state_path = root / 'setup-state.json'
    if root.exists() and any(root.iterdir()) and not state_path.exists():
        raise ValueError('Choose an empty folder. This folder belongs to another installation.')
    inventory = gpu_devices()
    gpu = max(inventory, key=lambda g: (g['discrete'], 'RTX' in g['name']), default={})
    use_dlss = gpu.get('vendor') == 0x10DE and 'RTX' in gpu.get('name', '')
    target_game = root / 'games/Ocarina of Time.nup'
    existing_parent = root
    while not existing_parent.exists():
        existing_parent = existing_parent.parent
    needed = (0 if target_game.exists() else details['size']) + 2 * 1024**3
    if shutil.disk_usage(existing_parent).free < needed:
        raise ValueError('Not enough free space for the selected game and setup files.')
    root.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({'version': VERSION, 'installing': True}, indent=2))
    download_cache = Path(cache) if cache else root / '.setup-downloads'
    download_cache.mkdir(parents=True, exist_ok=True)
    assets = manifest()
    runtime = fetch(assets['fritchii'], download_cache, status)
    status('Installing Fritchii ' + assets['fritchii']['version'])
    extract_zip(runtime, root, strip_top=True)
    sdl = fetch(assets['sdl'], download_cache, status)
    with zipfile.ZipFile(sdl) as package:
        name = next(n for n in package.namelist() if PurePosixPath(n).name == 'SDL3.dll')
        support = root / 'support'
        support.mkdir(exist_ok=True)
        (support / 'SDL3.dll').write_bytes(package.read(name))
    if use_dlss:
        sdk = fetch(assets['streamline'], download_cache, status)
        with zipfile.ZipFile(sdk) as package:
            destination = root / 'user/streamline'
            destination.mkdir(parents=True, exist_ok=True)
            for name in ['bin/x64/sl.interposer.dll', 'bin/x64/nvngx_dlss.dll',
                         'license.txt', 'bin/x64/nvngx_dlss.license.txt']:
                (destination / PurePosixPath(name).name).write_bytes(package.read(name))
    target_game.parent.mkdir(exist_ok=True)
    if target_game.exists():
        validate_game(target_game)
        status('Keeping the existing installed game and player data')
    else:
        status('Copying your game file; existing saves are not imported')
        partial = target_game.with_suffix('.nup.partial')
        shutil.copyfile(game, partial)
        partial.replace(target_game)
        validate_game(target_game)
    fresh_config(root, gpu, use_dlss)
    for source, destination in [('assets/ocarina.ico', 'support/ocarina.ico'),
                                ('assets/cover.png', 'games/Ocarina of Time.png'),
                                ('THIRD_PARTY.md', 'THIRD_PARTY.md'), ('LICENSE', 'SETUP-LICENSE.txt')]:
        shutil.copyfile(resource(source), root / destination)
    target_exe = root / 'Fritchii Launcher.exe'
    if executable.resolve() != target_exe.resolve():
        shutil.copyfile(executable, target_exe)
    # Use the VC redistributable included by the publisher only if its runtime is absent.
    if os.name == 'nt' and not (Path(os.environ['WINDIR']) / 'System32/msvcp140.dll').exists():
        status('Installing the Microsoft C++ runtime (Windows may ask for permission)')
        env = dict(os.environ, FRITCHII_REDIST=str(root / 'vc_redist.x64.exe'))
        code = "$p=Start-Process -FilePath $env:FRITCHII_REDIST -ArgumentList '/install','/passive','/norestart' -Verb RunAs -Wait -PassThru -WindowStyle Hidden; exit $p.ExitCode"
        with external_dlls():
            result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', code], env=env,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode not in (0, 3010):
            raise RuntimeError('The Microsoft C++ runtime installation was not completed.')
    if create_shortcuts:
        shortcuts(root)
    state_path.write_text(json.dumps({'version': VERSION, 'installing': False,
                                     'fritchii': assets['fritchii']['version'], 'gpu': gpu,
                                     'dlss': use_dlss, 'game': 'games/Ocarina of Time.nup'}, indent=2))
    status('Installation complete. Connect your controller before opening the desktop shortcut.')
    return root
