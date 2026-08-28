"""Knowing what your own speakers just did.

The detector cannot tell a hi-hat from a clap, because acoustically there isn't
much of a difference. Rather than get cleverer about that, we cheat: we also
listen to what the computer is *playing*. If the speakers produced a transient a
moment ago, the microphone is about to hear it, and that one doesn't count.

This is deliberately not acoustic echo cancellation. There's no adaptive filter
and nothing gets subtracted. We are not trying to remove your speakers from the
signal, only to recognise their handwriting.
"""

import collections
import platform
import threading

import numpy as np

from .detector import BLOCK, SR, ClapDetector


class SpeakerActivity:
    """Timestamps of recent speaker transients, and whether one is still warm.

    Pure bookkeeping, no audio - which is the only reason it's testable.
    """

    def __init__(self, hold=0.25):
        self.hold = hold          # s - covers speaker latency plus air travel
        self.marks = collections.deque(maxlen=64)
        self.total = 0            # lifetime count; marks expire, this doesn't

    def mark(self, when):
        self.marks.append(when)
        self.total += 1

    def blocks(self, now):
        """True if the speakers popped recently enough to explain what we heard."""
        while self.marks and now - self.marks[0] > self.hold:
            self.marks.popleft()
        return any(0.0 <= now - t <= self.hold for t in self.marks)


class LoopbackVeto:
    """Watches the speakers in a background thread. Fails politely.

    If the optional dependency is missing, or the platform has no loopback
    device, this turns itself off and says why instead of exploding.
    """

    def __init__(self, hold=0.25, sensitivity=2.0, device=None):
        self.activity = SpeakerActivity(hold=hold)
        self.sensitivity = sensitivity   # permissive on purpose: high recall
        self.device = device
        self.available = False
        self.reason = "not started"
        self.name = None
        self._stop = threading.Event()
        self._thread = None

    def start(self, clock):
        """Begin watching. Returns True if the speakers are actually being heard."""
        try:
            import soundcard
        except ImportError:
            self.reason = "soundcard not installed (pip install 'clapoff[loopback]')"
            return False
        except Exception as exc:                       # pragma: no cover
            self.reason = f"soundcard failed to load ({exc})"
            return False

        try:
            mics = soundcard.all_microphones(include_loopback=True)
            loops = [m for m in mics if getattr(m, "isloopback", False)]
            if not loops:
                self.reason = "no loopback device on this system"
                return False
            if self.device:
                target = next((m for m in loops if self.device.lower() in m.name.lower()), None)
                if target is None:
                    self.reason = f"no loopback device matching {self.device!r}"
                    return False
            else:
                try:
                    default = soundcard.default_speaker().name
                except Exception:                      # pragma: no cover
                    default = None
                target = next((m for m in loops if m.name == default), loops[0])
        except Exception as exc:                       # pragma: no cover
            self.reason = f"couldn't enumerate loopback devices ({exc})"
            return False

        self.name = target.name
        self.available = True
        self.reason = "watching"
        self._thread = threading.Thread(
            target=self._run, args=(target, clock), daemon=True, name="clapoff-loopback")
        self._thread.start()
        return True

    @staticmethod
    def _init_com():
        """WASAPI is COM, and COM is per-thread.

        soundcard initialises COM when it's imported, which happens on the main
        thread. Our capture lives on its own thread, where none of that ever
        happened, and the first call comes back 0x800401f0 (CO_E_NOTINITIALIZED)
        - which surfaces as the veto quietly switching itself off.
        """
        if platform.system() != "Windows":
            return
        import ctypes
        COINIT_MULTITHREADED = 0x0
        RPC_E_CHANGED_MODE = 0x80010106
        hr = ctypes.windll.ole32.CoInitializeEx(None, COINIT_MULTITHREADED) & 0xFFFFFFFF
        if hr == RPC_E_CHANGED_MODE:      # already apartment-threaded; fine either way
            return

    def _run(self, target, clock):                     # pragma: no cover - needs speakers
        self._init_com()
        det = ClapDetector(sensitivity=self.sensitivity)
        det.refractory = 0.05        # we want every pop, not one per burst
        try:
            with target.recorder(samplerate=SR, channels=1, blocksize=BLOCK) as rec:
                while not self._stop.is_set():
                    data = rec.record(numframes=BLOCK)
                    x = np.ascontiguousarray(data[:, 0], dtype=np.float32)
                    now = clock()
                    event = det.feed(x, now)
                    if event is not None and event[0] == "clap":
                        self.activity.mark(now)
        except Exception as exc:
            self.available = False
            self.reason = f"loopback capture stopped ({exc})"

    def blocks(self, now):
        return self.available and self.activity.blocks(now)

    def stop(self):
        self._stop.set()

    def status(self):
        if self.available:
            return f'watching "{self.name}"'
        return f"off - {self.reason}"
