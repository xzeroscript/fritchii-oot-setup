# Fritchii OOT Setup

One Windows setup file for Fritchii, a locally supplied Ocarina of Time game,
fresh player data, and automatic Xbox controller bindings.

**Download `Fritchii-OOT-Setup.exe` from [Releases](../../releases/latest).**

## Install

1. Run the setup file and select **your own Ocarina of Time `.nup`**.
2. Accept the third-party license terms and click **Install**.
3. Connect your controller and open **Ocarina of Time (Fritchii)** on the desktop.

Python, SDL, Fritchii and NVIDIA DLSS components need no separate manual install.
The setup downloads verified publisher archives automatically. On RTX cards it
installs DLSS; other GPUs keep the renderer's normal path. If Microsoft's C++
runtime is missing, its installation can request Windows administrator consent.

The first game launch prepares shaders. Let it finish; the publisher estimates
around 15 minutes on an eight-core CPU, with actual time depending on the system.
Updating from Fritchii v5.5 to v5.6 also requires this preparation once more.

No ROM, firmware, keys, shader dumps, shader cache, account profile or saves are
included in this repository or its release. A fresh installation starts without
player progress. Reinstalling keeps existing player data and settings.

## Included setup changes

- Controller bindings are checked on **every shortcut launch**, using the actual
  open joystick's identity and the relevant SDL backend settings used by Fritchii.
  Reconnecting through a different controller identity no longer leaves the
  original one-time setup marker blocking a repair. Current custom bindings are
  retained while they refer to the same device.
- Vulkan adapter selection follows the actual adapter enumeration and prefers a
  discrete GPU. RTX cards receive DLSS preset K. A fresh setup selects docked,
  1x resolution scale and the runner's normal 60 FPS mode.
- The built-in Max Resolution add-on is disabled on a fresh setup to avoid its
  additional 4K rendering load. Normal emulation speed is 100 percent; that is
  **not a 100 FPS cap**.
- Game and library desktop shortcuts and the supplied local home-cover artwork.
- Public download hashes are pinned in `manifest.json`. Archive extraction rejects
  traversal and symlinks before writing files.

The custom Xbox **font/UI mod is not installed** while its possible involvement
in dialogue corruption is being compared. The physical Xbox bindings still work:
Switch B is Xbox A, Switch A is Xbox B, Switch Y is Xbox X, and Switch X is Xbox Y.

## Known limits

This is a **setup helper**, not a patched Fritchii emulator. Dialogue corruption
after switching UIs and stalls during combat/cutscenes/interactions remain under
investigation. No claim that this produces a perfectly stable frame rate is made.
Setup v0.1.1 downloads the publisher's **Fritchii v5.6 pre-release**, which fixes one
cause of the growing white light beams and includes compute-pipeline stall and
memory cleanup improvements. Its release notes explicitly say light beams can
still appear in long sessions; this has not been verified fixed in every scene.
The failed texture-relocation override, developer CPU sampler, game-frame capture,
personal diagnostic files and local caches are deliberately not enabled here.

Requires Windows x64, an internet connection, supported Vulkan graphics drivers,
and space for your game plus approximately 2 GB during installation. The executable
is unsigned, so Windows may display its normal unknown-publisher warning.
Allow additional space for shader and driver caches on the first game launch.

Fritchii is downloaded unmodified from
[Frizti/Fritchii](https://github.com/Frizti/Fritchii/releases/tag/fritchii-v5.6).
This project is independent of that publisher and Nintendo.

## Build from source

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m PyInstaller --noconfirm FritchiiSetup.spec
```

The output is `dist/Fritchii-OOT-Setup.exe`. The same executable is installed as
the local launcher, so the installed controller helper does not require Python
to be installed on the player's PC. `--self-test <json-file>` validates bundled
resources without opening a GUI or launching a game.

Publish a tag such as `v0.1.1` to build and attach the Windows installer and its
SHA256 checksum through GitHub Actions. Game files must never be committed.

The setup code is MIT licensed. See [third-party notices](THIRD_PARTY.md) for
upstream software, runtime licenses and the separate artwork notice.
