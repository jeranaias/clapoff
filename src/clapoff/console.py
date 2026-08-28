"""Beeps and keypresses, which every operating system does differently."""

import platform
import sys
import threading
import time

_WINDOWS = platform.system() == "Windows"

if _WINDOWS:
    import msvcrt
    import winsound
else:
    msvcrt = None
    winsound = None
    try:
        import select
        import termios
        import tty
    except ImportError:      # pragma: no cover - very unusual POSIX
        termios = None


def beep(freq=1000, ms=90):
    """Make a noise. Non-blocking, because the audio loop can't wait around."""
    if winsound is not None:
        threading.Thread(target=winsound.Beep, args=(freq, ms), daemon=True).start()
    else:
        sys.stdout.write("\a")
        sys.stdout.flush()


def say(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def key_pressed():
    """True if someone hit a key. Never blocks; returns False when there's no tty."""
    if msvcrt is not None:
        if msvcrt.kbhit():
            msvcrt.getch()
            return True
        return False
    if termios is None or not sys.stdin.isatty():
        return False
    try:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            if select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.read(1)
                return True
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except (termios.error, ValueError, OSError):
        return False
    return False


def drain_keys():
    """Throw away buffered keystrokes so an old one can't abort a fresh countdown."""
    if msvcrt is not None:
        while msvcrt.kbhit():
            msvcrt.getch()
