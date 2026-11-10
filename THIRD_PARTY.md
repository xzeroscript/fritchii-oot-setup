# Third-party software

This installer downloads software directly from its original publisher and
checks each archive against its pinned SHA256. The GitHub release does not
contain the game, firmware, keys, shader caches or another person's saves.

- Fritchii v5.6: https://github.com/Frizti/Fritchii/releases/tag/fritchii-v5.6
  Source and licenses: https://github.com/Frizti/Fritchii/tree/fritchii-v5.6
  Fritchii/Lichii and its dependencies retain their own licenses. The helper
  is independent and is not an official Fritchii release.
- SDL 3.4.20: https://github.com/libsdl-org/SDL/releases/tag/release-3.4.20
  zlib license; included under licenses/SDL.txt.
- NVIDIA Streamline 2.14.16 and DLSS: downloaded only for a detected RTX GPU.
  https://github.com/NVIDIA-RTX/Streamline/releases/tag/v2.14.16
  NVIDIA's Streamline and DLSS license terms are included in the installer
  and copied with the downloaded runtime. No NVIDIA frame generation is added.
- Microsoft Visual C++ runtime: the redistributable provided in Fritchii's
  official archive is installed only if the runtime is missing. Windows may
  request administrator consent for this prerequisite.
- Python/Tk and PyInstaller power this standalone setup. Python and Tcl/Tk
  retain their own licenses; PyInstaller has its bootloader exception.
  https://docs.python.org/3/license.html
  https://pyinstaller.org/en/stable/license.html

Cover artwork was supplied for this setup's icon. It is not covered by the
setup code's MIT license; ownership remains with its respective creators.
