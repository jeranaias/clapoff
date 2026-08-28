"""The part that decides whether that noise was a clap.

Pure numpy on purpose - no audio library, no microphone, no operating system.
That means the tests can run anywhere, including CI machines that have never
heard a sound in their lives.
"""

import collections

import numpy as np

SR = 16000      # sample rate
BLOCK = 256     # 16 ms of audio per block
HF_CUT = 2000   # Hz - a clap keeps most of its energy above here
EPS = 1e-12


class ClapDetector:
    """Spots short broadband transients and, more importantly, ignores everything else.

    The trick is that "loud" is useless as a threshold. If you set an absolute
    level, the detector works beautifully in a silent room and goes completely
    deaf the moment you put music on, because now *every* block is loud and
    nothing ever looks like an onset.

    So instead we compare each block's high-frequency energy against a rolling
    median of the last three quarters of a second. A clap spikes above whatever
    the room is already doing. Then we watch what happens next: real claps are
    over in milliseconds. If the spike is still going 225 ms later, it wasn't a
    clap, it was a chord, and we take the detection back.
    """

    def __init__(self, sensitivity=1.0, hf_min=0.25):
        self.ratio = 8.0 / sensitivity      # HF spike must beat the background by this
        self.abs_min = 0.008 / sensitivity  # ...and clear this absolute RMS
        self.hf_min = hf_min                # fraction of block energy above HF_CUT
        self.refractory = 0.12              # s - one clap, not its echo
        self.max_loud_blocks = 14           # ~225 ms; longer than this isn't a clap

        self.window = np.hanning(BLOCK).astype(np.float32)
        freqs = np.fft.rfftfreq(BLOCK, 1.0 / SR)
        self.hf_mask = freqs >= HF_CUT

        self.hist = collections.deque(maxlen=int(0.75 * SR / BLOCK))
        self.loud_run = 0
        self.last_clap_t = 0.0
        self.pending = False

    def feed(self, x, now):
        """Push one block of mono float samples.

        Returns ``("clap", rms, hf_fraction, spike)``, ``("retract", ...)`` when
        a previous detection turns out to have been noise, or ``None``.
        """
        rms = float(np.sqrt(np.mean(x * x)))
        spec = np.abs(np.fft.rfft(x * self.window)) ** 2
        hf_e = float(spec[self.hf_mask].sum())
        hf_frac = hf_e / (float(spec.sum()) + EPS)

        if len(self.hist) < self.hist.maxlen:    # ~0.75 s of warm-up
            self.hist.append(hf_e)
            return None
        bg = float(np.median(self.hist)) + EPS
        self.hist.append(hf_e)

        spike = hf_e / bg
        if spike > 3.0:
            self.loud_run += 1
        else:
            self.loud_run = 0
            self.pending = False

        event = None
        if (spike > self.ratio and rms > self.abs_min and hf_frac >= self.hf_min
                and self.loud_run <= 3                      # this is the attack itself
                and now - self.last_clap_t > self.refractory):
            self.last_clap_t = now
            self.pending = True
            event = ("clap", rms, hf_frac, spike)
        elif self.pending and self.loud_run > self.max_loud_blocks:
            self.pending = False                            # never decayed, so: not a clap
            event = ("retract", rms, hf_frac, spike)
        return event
