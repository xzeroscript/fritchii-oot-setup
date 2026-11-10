import configparser
import hashlib
from pathlib import Path
import struct
import io
import zipfile

import pytest
import core


def fixture_game(path: Path, title=core.TITLE_ID):
    toc = bytearray(112)
    toc[:4] = b'TOC\x01'
    struct.pack_into('<I', toc, 4, 1)
    struct.pack_into('<Q', toc, 48, title)
    header = bytearray(128)
    header[:4] = b'NUP\x01'
    struct.pack_into('<HHQQ', header, 4, 128, 1, 128, len(toc))
    header[24:56] = hashlib.sha256(toc).digest()
    struct.pack_into('<QQI', header, 56, 240, 240, 1)
    path.write_bytes(header + toc)
    return path


def test_valid_game_and_corruption_detection(tmp_path):
    path = fixture_game(tmp_path / 'own game [update].nup')
    assert core.validate_game(path)['packages'] == 1
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(data)
    with pytest.raises(ValueError, match='checksum'):
        core.validate_game(path)


def test_rejects_other_games(tmp_path):
    path = fixture_game(tmp_path / 'other.nup', title=1234)
    with pytest.raises(ValueError, match='title'):
        core.validate_game(path)


@pytest.mark.parametrize('unsafe', ['../outside.txt', '/outside.txt', 'C:/outside.txt', '..\\outside.txt'])
def test_archive_validated_before_any_write(tmp_path, unsafe):
    archive = tmp_path / 'archive.zip'
    with zipfile.ZipFile(archive, 'w') as out:
        out.writestr('safe.txt', 'safe')
        out.writestr(unsafe, 'bad')
    destination = tmp_path / 'destination'
    with pytest.raises(ValueError):
        core.extract_zip(archive, destination)
    assert not destination.exists()


def test_first_install_has_no_saves_and_reinstall_preserves_data(tmp_path):
    core.fresh_config(tmp_path, {'index': 2}, True)
    ini = tmp_path / 'user/config/qt-config.ini'
    c = configparser.RawConfigParser()
    c.read(ini)
    assert c['Renderer']['vulkan_device'] == '2'
    assert c['Renderer']['nvidia_dlss'] == 'true'
    assert not (tmp_path / 'user/nand').exists()
    save = tmp_path / 'user/nand/example.sav'
    save.parent.mkdir()
    save.write_bytes(b'existing player progress')
    before = ini.read_bytes()
    core.fresh_config(tmp_path, {}, False)
    assert ini.read_bytes() == before
    assert save.read_bytes() == b'existing player progress'


def test_controller_uses_actual_device_identity():
    from controller import make_mapping
    mapping = ('030000005e040000ff02000000007801,Xbox,a:b0,b:b1,x:b2,y:b3,'
               'leftshoulder:b4,rightshoulder:b5,back:b6,start:b7,leftstick:b8,rightstick:b9,'
               'lefttrigger:a2,righttrigger:a5,leftx:a0,lefty:a1,rightx:a3,righty:a4,')
    actual = '0300fa675e040000220b000013057801'
    result = make_mapping(mapping, actual)
    assert all('guid:030000005e040000220b000013057801' in v for v in result.values())
    assert result['player_0_button_b'].endswith('button:0')
    assert ',axis_x:3,axis_y:4,' in result['player_0_rstick']


def test_failed_download_hash_is_not_installed(tmp_path, monkeypatch):
    class Response(io.BytesIO):
        headers = {}
    monkeypatch.setattr(core.urllib.request, 'urlopen', lambda *a, **k: Response(b'wrong package'))
    asset = {'name': 'publisher.zip', 'url': 'https://example.invalid/publisher.zip', 'sha256': '0'*64}
    with pytest.raises(ValueError, match='checksum'):
        core.fetch(asset, tmp_path, lambda s: None)
    assert not (tmp_path / 'publisher.zip').exists()
    assert not (tmp_path / 'publisher.zip.partial').exists()
