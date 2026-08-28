"""A little coloured dot that tells you it's listening.

Running hidden solves the "no console" problem by removing the console, which
also removes every sign that the program exists at all. A tray icon puts it
back: you can see the state, pause it when you're about to applaud something,
and quit it without hunting through Task Manager.

Optional. If pystray isn't installed, this reports why and everything else
carries on exactly as before.
"""

import threading

COLOURS = {
    "listening": (90, 180, 120),     # green: awake, nothing happening
    "heard": (245, 200, 70),         # amber: that was a clap
    "countdown": (220, 80, 80),      # red: something is about to happen
    "paused": (120, 120, 120),       # grey: deliberately ignoring you
}


def _draw(colour):
    from PIL import Image, ImageDraw
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((6, 6, 58, 58), fill=colour + (255,))
    return image


class Tray:
    """The dot. Everything about it is best-effort."""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.available = False
        self.reason = "disabled" if not enabled else "not started"
        self.paused = False
        self.quit_requested = False
        self._icon = None
        self._state = None
        self._lock = threading.Lock()

    def start(self):
        if not self.enabled:
            return False
        try:
            import pystray
            from PIL import Image  # noqa: F401  - checked here so the error is clear
        except ImportError:
            self.reason = "pystray not installed (pip install 'clapoff[tray]')"
            return False
        try:
            menu = pystray.Menu(
                pystray.MenuItem(lambda _: "Paused" if self.paused else "Listening",
                                 self._toggle, checked=lambda _: not self.paused),
                pystray.MenuItem("Quit", self._quit),
            )
            self._icon = pystray.Icon("clapoff", _draw(COLOURS["listening"]),
                                      "clapoff - listening", menu)
            if hasattr(self._icon, "run_detached"):
                self._icon.run_detached()
            else:                                    # pragma: no cover - platform dependent
                threading.Thread(target=self._icon.run, daemon=True).start()
        except Exception as exc:                     # pragma: no cover - no desktop
            self.reason = f"no system tray available ({exc})"
            return False
        self.available = True
        self.reason = "showing"
        self._state = "listening"
        return True

    def _toggle(self, *_):
        self.paused = not self.paused
        self.set_state("paused" if self.paused else "listening")

    def _quit(self, *_):
        self.quit_requested = True
        self.stop()

    def set_state(self, state):
        """Repaint, but only when something actually changed."""
        if not self.available or state == self._state:
            return
        with self._lock:
            self._state = state
            try:
                self._icon.icon = _draw(COLOURS.get(state, COLOURS["listening"]))
                self._icon.title = f"clapoff - {state}"
            except Exception:                        # pragma: no cover
                pass

    def stop(self):
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:                        # pragma: no cover
                pass
        self.available = False

    def status(self):
        return "showing" if self.available else f"off - {self.reason}"
