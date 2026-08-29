"""Getting 16 kHz out of a microphone that has never heard of 16 kHz.

The detector works at 16 kHz because that puts the interesting part of a clap
comfortably inside the band and keeps the FFTs small. Plenty of hardware simply
won't open there. WASAPI in shared mode plays back whatever rate the device is
configured for and rejects anything else outright:

    Error opening InputStream: Invalid sample rate [PaErrorCode -9997]

So: try the rate we want, and if the device refuses, open at whatever it does
want and resample on the way in. The rest of the program never finds out.
"""

import numpy as np

from .detector import BLOCK, SR


def resample(frames, out_len):
    """Resample (n, channels) audio to `out_len` frames.

    Downsampling gets a moving average first. Dropping samples without one folds
    everything above the new Nyquist back down into the band we're measuring,
    and since the whole detector is "is there suddenly a lot of high frequency
    energy", aliasing would land squarely on the thing being measured.
    """
    frames = np.asarray(frames, dtype=np.float32)
    if frames.ndim == 1:
        frames = frames[:, None]
    n_in = frames.shape[0]
    if n_in == out_len or n_in == 0:
        return frames.astype(np.float32, copy=False)

    if n_in > out_len:
        width = max(1, int(round(n_in / out_len)))
        if width > 1:
            kernel = np.ones(width, dtype=np.float32) / width
            frames = np.stack(
                [np.convolve(frames[:, c], kernel, mode="same") for c in range(frames.shape[1])],
                axis=1)

    src = np.linspace(0.0, 1.0, n_in, dtype=np.float64)
    dst = np.linspace(0.0, 1.0, out_len, dtype=np.float64)
    return np.stack([np.interp(dst, src, frames[:, c]) for c in range(frames.shape[1])],
                    axis=1).astype(np.float32)


class Input:
    """An input stream that always hands you BLOCK frames at SR.

    Same shape as a sounddevice stream from the caller's point of view: use it
    as a context manager, call read(BLOCK), get (frames, overflowed) back.
    """

    def __init__(self, sd, device=None, channels=1):
        self.sd = sd
        self.device = device
        self.channels = channels
        self.rate = SR
        self.native_block = BLOCK
        self.resampling = False
        self._stream = None

    def _device_rate(self):
        try:
            info = self.sd.query_devices(
                self.device if self.device is not None else self.sd.default.device[0],
                "input")
            rate = int(round(float(info["default_samplerate"])))
            return rate if rate > 0 else 48000
        except Exception:
            return 48000

    def __enter__(self):
        def build(rate):
            block = int(round(BLOCK * rate / SR))
            stream = self.sd.InputStream(samplerate=rate, blocksize=block,
                                         channels=self.channels, dtype="float32",
                                         device=self.device)
            stream.start()
            return stream, rate, block

        try:
            self._stream, self.rate, self.native_block = build(SR)
        except Exception:
            # Almost always PaErrorCode -9997. Take the rate the device offers.
            self._stream, self.rate, self.native_block = build(self._device_rate())
            self.resampling = True
        return self

    def read(self, _frames=BLOCK):
        data, overflowed = self._stream.read(self.native_block)
        if self.resampling:
            data = resample(data, BLOCK)
        return data, overflowed

    def __exit__(self, *_):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
        return False

    def describe(self):
        if not self.resampling:
            return f"{self.rate} Hz"
        return f"{self.rate} Hz, resampled to {SR}"
