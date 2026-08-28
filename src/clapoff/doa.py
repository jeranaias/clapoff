"""Where the clap came from.

With two or more real microphones you can tell a clap from the couch apart from
a clap from the television, because sound takes about 3 samples per centimetre
of spacing to get from one capsule to the other. Cross-correlate the channels,
read off the delay, and you have a fingerprint of a direction.

The catch, and it's a big one: most laptop "microphone arrays" beamform in the
driver and hand you one processed mono stream copied across every channel. They
look like arrays and contain no spatial information whatsoever. So this module
leads with a probe that says so out loud, rather than quietly gating on noise.
"""

import numpy as np

DEAD_RMS = 1e-4          # below this a channel isn't listening to anything
DUPLICATE_CORR = 0.999   # above this two channels are the same signal twice


def gcc_phat(a, b, max_shift=None):
    """Delay of `a` relative to `b`, in samples, plus a confidence ratio.

    PHAT weighting throws away magnitude and keeps only phase, which is what
    makes this hold up on a broadband transient in a reverberant room - exactly
    the signal we have.
    """
    n = len(a) + len(b)
    A = np.fft.rfft(a, n)
    B = np.fft.rfft(b, n)
    R = A * np.conj(B)
    mag = np.abs(R)
    mag[mag < 1e-12] = 1e-12
    cc = np.fft.irfft(R / mag, n)

    limit = max_shift if max_shift is not None else n // 2
    limit = max(1, min(limit, n // 2 - 1))
    window = np.concatenate([cc[-limit:], cc[:limit + 1]])
    idx = int(np.argmax(np.abs(window)))
    peak = float(np.abs(window[idx]))
    confidence = peak / (float(np.abs(window).mean()) + 1e-12)
    return idx - limit, confidence


def signature(frames, max_shift=16):
    """Delay of every channel relative to channel 0. The direction fingerprint."""
    frames = np.asarray(frames, dtype=np.float64)
    if frames.ndim != 2 or frames.shape[1] < 2:
        return []
    reference = frames[:, 0]
    return [gcc_phat(frames[:, j], reference, max_shift)[0]
            for j in range(1, frames.shape[1])]


def array_report(frames):
    """Is this actually an array, or one microphone wearing four hats?"""
    frames = np.asarray(frames, dtype=np.float64)
    if frames.ndim != 2 or frames.shape[1] < 2:
        return {"usable": False, "reason": "only one channel", "channels": []}

    rms = np.sqrt((frames ** 2).mean(axis=0))
    reference = frames[:, 0]
    channels = []
    for j in range(frames.shape[1]):
        entry = {"channel": j, "rms": float(rms[j])}
        if rms[j] < DEAD_RMS:
            entry["verdict"] = "silent"
        elif j == 0:
            entry["verdict"] = "reference"
        elif np.std(reference) < 1e-9 or np.std(frames[:, j]) < 1e-9:
            entry["verdict"] = "flat"
        else:
            corr = float(np.corrcoef(reference, frames[:, j])[0, 1])
            entry["corr"] = corr
            entry["verdict"] = "duplicate of ch0" if abs(corr) > DUPLICATE_CORR else "independent"
        channels.append(entry)

    live = [c for c in channels if c["verdict"] in ("reference", "independent")]
    if len(live) >= 2:
        return {"usable": True, "reason": f"{len(live)} independent channels",
                "channels": channels}
    duplicates = sum(1 for c in channels if c["verdict"] == "duplicate of ch0")
    if duplicates:
        reason = ("the driver is beamforming for you - every channel is the same "
                  "signal, so there's no direction left to recover")
    else:
        reason = "not enough live channels"
    return {"usable": False, "reason": reason, "channels": channels}


class DirectionGate:
    """Accept claps whose delay fingerprint matches the one you trained.

    Off unless it was trained *and* the hardware can actually support it, which
    is the whole point of the probe above.
    """

    def __init__(self, reference=None, tolerance=2.0):
        self.reference = list(reference) if reference else None
        self.tolerance = tolerance      # samples; ~2 is a few centimetres

    @property
    def active(self):
        return bool(self.reference)

    def accepts(self, observed):
        if not self.active:
            return True                 # untrained means everything is welcome
        if not observed or len(observed) != len(self.reference):
            return True                 # channel count changed; don't start lying
        return all(abs(o - r) <= self.tolerance
                   for o, r in zip(observed, self.reference))

    def status(self):
        if not self.active:
            return "off - not trained (run: clapoff --train-direction)"
        return f"only claps from {self.reference} (+/- {self.tolerance:g} samples)"
