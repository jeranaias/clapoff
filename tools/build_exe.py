"""Build the single-file Windows download.

    python tools/build_exe.py

Produces dist/clapoff.exe: no Python, no pip, no dependencies to install.
"""

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile",
        "--windowed",                       # no console window on double-click
        "--name", "clapoff",
        "--icon", str(ROOT / "assets" / "clapoff.ico"),
        "--paths", str(ROOT / "src"),
        # PortAudio arrives as a data file inside sounddevice, which the
        # dependency scanner has no way of noticing on its own.
        "--collect-all", "sounddevice",
        "--collect-all", "soundcard",
        "--collect-all", "pystray",
        "--hidden-import", "clapoff",
        str(ROOT / "packaging" / "launcher.py"),
    ]
    print(" ".join(args))
    return subprocess.call(args, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
