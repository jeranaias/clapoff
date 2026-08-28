"""Synthetic audio in, verdicts out. No microphone, no speakers, no clapping."""

import numpy as np
import pytest

from clapoff.detector import BLOCK, SR, ClapDetector

RNG_SEED = 0


def rng():
    return np.random.default_rng(RNG_SEED)


def room_tone(sec, level=0.002, r=None):
    r = r or rng()
    return r.normal(0, level, int(SR * sec)).astype(np.float32)


def clap(level=0.35, r=None):
    """Broadband burst with a ~12 ms decay constant. What a clap actually is."""
    r = r or rng()
    n = int(SR * 0.05)
    t = np.arange(n) / SR
    return (r.normal(0, level, n) * np.exp(-t / 0.012)).astype(np.float32)


def music(sec, level=0.12, r=None):
    """Loud, tonal, low-frequency, and crucially it never stops."""
    r = r or rng()
    t = np.arange(int(SR * sec)) / SR
    sig = sum(np.sin(2 * np.pi * f * t) for f in (110, 220, 330, 440))
    return (level * sig / 4 + r.normal(0, level * 0.15, t.size)).astype(np.float32)


def thump(level=0.5):
    """A door, a footstep, a dropped book. Loud but all bass."""
    n = int(SR * 0.12)
    t = np.arange(n) / SR
    return (level * np.sin(2 * np.pi * 90 * t) * np.exp(-t / 0.04)).astype(np.float32)


def count(signal, sensitivity=1.0):
    """Run a signal through the detector; return (claps, retractions)."""
    det = ClapDetector(sensitivity=sensitivity)
    claps = retracted = 0
    now = 0.0
    for i in range(0, len(signal) - BLOCK, BLOCK):
        now += BLOCK / SR
        event = det.feed(signal[i:i + BLOCK], now)
        if event is None:
            continue
        if event[0] == "clap":
            claps += 1
        else:
            retracted += 1
    return claps, retracted


def cat(*parts):
    return np.concatenate(parts)


# --- things it must hear -----------------------------------------------------

def test_three_claps_in_a_quiet_room():
    sig = cat(room_tone(1.0), clap(), room_tone(0.4), clap(),
              room_tone(0.4), clap(), room_tone(0.5))
    assert count(sig)[0] == 3


def test_quiet_claps_from_across_the_room():
    sig = cat(room_tone(1.0), clap(0.12), room_tone(0.3), clap(0.12),
              room_tone(0.3), clap(0.12), room_tone(0.5))
    assert count(sig)[0] == 3


def test_claps_while_music_is_playing():
    """The regression that motivated the rolling-median background."""
    sig = cat(music(2.0), clap(0.5), music(0.4), clap(0.5),
              music(0.4), clap(0.5), music(0.5))
    assert count(sig)[0] == 3


# --- things it must ignore ---------------------------------------------------

def test_music_alone_is_not_a_clap():
    assert count(cat(room_tone(1.0), music(4.0), room_tone(0.5)))[0] == 0


def test_bass_thumps_are_not_claps():
    sig = cat(room_tone(1.0), thump(), room_tone(0.5), thump(),
              room_tone(0.5), thump(), room_tone(0.5))
    assert count(sig)[0] == 0


def test_silence_is_not_a_clap():
    assert count(room_tone(6.0))[0] == 0


def test_loud_tonal_bursts_are_not_claps():
    """Shouting, a TV, a doorbell - loud and abrupt, but they sustain."""
    sig = cat(room_tone(1.0), music(0.6, 0.25), room_tone(0.3), music(0.6, 0.25),
              room_tone(0.3), music(0.6, 0.25), room_tone(0.5))
    assert count(sig)[0] == 0


# --- knobs -------------------------------------------------------------------

def test_warmup_is_silent():
    """The first ~0.75 s fills the background buffer and can't fire."""
    det = ClapDetector()
    sig = clap(1.0)
    events = [det.feed(sig[i:i + BLOCK], i / SR) for i in range(0, len(sig) - BLOCK, BLOCK)]
    assert all(e is None for e in events)


def test_lower_sensitivity_hears_less():
    sig = cat(room_tone(1.0), clap(0.05), room_tone(0.3), clap(0.05),
              room_tone(0.3), clap(0.05), room_tone(0.5))
    assert count(sig, sensitivity=2.0)[0] >= count(sig, sensitivity=0.25)[0]


@pytest.mark.parametrize("level", [0.08, 0.2, 0.5, 1.0])
def test_claps_detected_across_volumes(level):
    sig = cat(room_tone(1.0), clap(level), room_tone(0.5))
    assert count(sig)[0] == 1
