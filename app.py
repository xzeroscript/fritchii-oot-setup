"""One-file Windows setup and installed launcher. No game is distributed."""
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

import core


def running():
    with core.external_dlls():
        result = subprocess.run(['tasklist.exe', '/FI', 'IMAGENAME eq lichii.exe', '/FO', 'CSV', '/NH'],
                                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return '"lichii.exe"' in result.stdout.lower()


def launch(root: Path, library=False):
    if running():
        raise RuntimeError('Fritchii is already open. Use its Play button, or close it before using this shortcut.')
    if not (root / 'lichii.exe').is_file():
        raise RuntimeError('Fritchii is not installed here. Run the setup file first.')
    import controller
    folder = root / 'support'
    folder.mkdir(exist_ok=True)
    with (folder / 'controller-detection.log').open('w', encoding='utf-8') as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            controller.main(root)
    args = [str(root / 'lichii.exe')]
    if not library:
        args += ['-f', '-g', str(root / 'games/Ocarina of Time.nup')]
    with core.external_dlls():
        subprocess.Popen(args, cwd=root)


def setup_ui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
    root = tk.Tk()
    root.title('Fritchii + Ocarina of Time Setup')
    root.geometry('650x480')
    root.minsize(650, 480)
    try:
        root.iconbitmap(str(core.resource('assets/ocarina.ico')))
    except tk.TclError:
        pass
    style = ttk.Style(root)
    if 'vista' in style.theme_names():
        style.theme_use('vista')
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Fritchii + Ocarina of Time', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='One setup file. Fresh player data. Xbox controller detection.',
              wraplength=590).pack(anchor='w', pady=(4, 16))
    ttk.Label(frame, text='Select your own Ocarina of Time .nup game file:').pack(anchor='w')
    game = tk.StringVar()
    row = ttk.Frame(frame)
    row.pack(fill='x', pady=(5, 12))
    game_entry = ttk.Entry(row, textvariable=game)
    game_entry.pack(side='left', fill='x', expand=True)
    ttk.Button(row, text='Browse…', command=lambda: game.set(filedialog.askopenfilename(
        title='Select your Ocarina of Time game', filetypes=[('NUP game', '*.nup')]) or game.get())).pack(side='right', padx=(8, 0))
    folder = tk.StringVar(value=str(Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Programs/Fritchii-OOT'))
    ttk.Label(frame, text='Install folder:').pack(anchor='w')
    row = ttk.Frame(frame)
    row.pack(fill='x', pady=(5, 12))
    ttk.Entry(row, textvariable=folder).pack(side='left', fill='x', expand=True)
    ttk.Button(row, text='Change…', command=lambda: folder.set(filedialog.askdirectory(
        title='Choose an empty installation folder') or folder.get())).pack(side='right', padx=(8, 0))
    ttk.Label(frame, text='Requires internet and space for your game plus 2 GB. Downloads come from the original publishers. No ROM, saves, keys or firmware are included.',
              wraplength=590).pack(anchor='w', pady=(0, 9))

    def licenses():
        window = tk.Toplevel(root)
        window.title('Setup and third-party licenses')
        window.geometry('760x540')
        text = scrolledtext.ScrolledText(window, wrap='word', padx=12, pady=12)
        text.pack(fill='both', expand=True)
        parts = [core.resource('LICENSE').read_text(encoding='utf-8'),
                 core.resource('THIRD_PARTY.md').read_text(encoding='utf-8')]
        parts += [p.read_text(encoding='utf-8', errors='replace') for p in sorted(core.resource('licenses').glob('*.txt'))]
        text.insert('1.0', '\n\n'.join(parts))
        text.configure(state='disabled')

    agreed = tk.BooleanVar(value=False)
    row = ttk.Frame(frame)
    row.pack(fill='x')
    ttk.Checkbutton(row, text='I accept the setup and third-party license terms.', variable=agreed).pack(side='left')
    ttk.Button(row, text='Read licenses', command=licenses).pack(side='right')
    status = tk.StringVar(value='Ready. No other software needs to be installed manually.')
    ttk.Label(frame, textvariable=status, wraplength=590).pack(anchor='w', pady=(14, 6))
    progress = ttk.Progressbar(frame, mode='indeterminate')
    progress.pack(fill='x')
    events = queue.Queue()
    installing = False

    def worker(target, source):
        try:
            if not getattr(sys, 'frozen', False):
                raise RuntimeError('Build the Windows executable before using the installer.')
            core.install(target, source, Path(sys.executable), lambda s: events.put(('status', s)))
            events.put(('done', str(target)))
        except Exception as exc:
            events.put(('error', str(exc)))

    def begin():
        nonlocal installing
        if not agreed.get():
            messagebox.showinfo('License terms', 'Read and accept the license terms before installing.', parent=root)
            return
        try:
            if running():
                raise RuntimeError('Close Fritchii before installing. Setup will not close it for you.')
            core.validate_game(Path(game.get()))
        except Exception as exc:
            messagebox.showerror('Cannot install', str(exc), parent=root)
            return
        installing = True
        button.configure(state='disabled')
        progress.start(12)
        threading.Thread(target=worker, args=(Path(folder.get()), Path(game.get())), daemon=True).start()

    def poll():
        nonlocal installing
        while True:
            try:
                kind, value = events.get_nowait()
            except queue.Empty:
                break
            if kind == 'status':
                status.set(value)
            else:
                installing = False
                progress.stop()
                button.configure(state='normal')
                if kind == 'done':
                    status.set('Installed. Connect your controller and open the Ocarina of Time desktop shortcut. The first game launch prepares shaders.')
                    button.configure(text='Close', command=root.destroy)
                else:
                    status.set('Setup stopped; you can retry. Existing saves were retained.')
                    messagebox.showerror('Setup could not finish', value, parent=root)
        root.after(100, poll)

    button = ttk.Button(frame, text='Install', command=begin)
    button.pack(anchor='e', pady=(15, 0))
    def close():
        if not installing:
            root.destroy()
        else:
            messagebox.showinfo('Installation running', 'Wait for the current installation step to finish.', parent=root)
    root.protocol('WM_DELETE_WINDOW', close)
    candidates = list(Path(sys.executable).parent.glob('*.nup'))
    if len(candidates) == 1:
        game.set(str(candidates[0]))
    root.after(100, poll)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--play', action='store_true')
    parser.add_argument('--library', action='store_true')
    parser.add_argument('--self-test', type=Path)
    args = parser.parse_args()
    if args.self_test:
        import controller
        import tkinter
        interpreter = tkinter.Tcl()  # No Tk window is created.
        assets = core.manifest()
        assert core.resource('assets/ocarina.ico').is_file()
        assert all(len(a['sha256']) == 64 for a in assets.values())
        args.self_test.write_text(json.dumps({'ok': True, 'version': core.VERSION,
                                             'bundled_controller': callable(controller.main),
                                             'bundled_assets': True,
                                             'tcl': interpreter.eval('info patchlevel')}, indent=2))
        return
    if args.play or args.library:
        try:
            launch(Path(sys.executable).resolve().parent, library=args.library)
        except Exception as exc:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(exc), 'Fritchii launcher', 0x10)
    else:
        setup_ui()


if __name__ == '__main__':
    main()
