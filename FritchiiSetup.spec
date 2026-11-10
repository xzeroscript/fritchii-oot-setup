from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / 'app.py')], pathex=[str(root)],
             binaries=[], datas=[(str(root / 'manifest.json'), '.'),
                                  (str(root / 'LICENSE'), '.'),
                                  (str(root / 'THIRD_PARTY.md'), '.'),
                                  (str(root / 'assets'), 'assets'),
                                  (str(root / 'licenses'), 'licenses')],
             hiddenimports=['controller'], hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name='Fritchii-OOT-Setup', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False,
          icon=str(root / 'assets/ocarina.ico'))
