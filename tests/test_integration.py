"""Driving main() with a fake microphone.

Everything else in the suite tests a part. This one runs the actual command-line
entry point end to end - detector, rhythm match, countdown, action - by handing
it a sounddevice module that plays synthetic claps instead of listening to a
room. No hardware, no hands, no clapping.
"""

import sys
import types

import numpy as np
import pytest

from clapoff.detector import BLOCK, SR

RNG = np.random.default_rng(0)


def room(sec, level=0.002):
    return RNG.normal(0, level, int(SR * sec)).astype(np.float32)


def clap(level=0.35):
    n = int(SR * 0.05)
    t = np.arange(n) / SR
    return (RNG.normal(0, level, n) * np.exp(-t / 0.012)).astype(np.float32)


def even_triple(gap=0.30):
    """clap-clap-clap: the 1:1 rhythm, which means shutdown."""
    pad = room(gap - 0.05)
    return np.concatenate([room(1.2), clap(), pad, clap(), pad, clap(), room(2.0)])


class Clock:
    """Time, derived from how much audio has been consumed.

    A real stream delivers a block every 16 ms, so wall-clock and audio time run
    together. A fake one delivers six seconds of audio in a millisecond, and then
    the detector's 120 ms refractory window swallows claps two and three. So the
    fake stream drives the clock, and everything downstream behaves as if this
    were happening at the speed of sound rather than the speed of the CPU.
    """

    def __init__(self):
        self.t = 0.0

    def advance(self, seconds):
        self.t += seconds

    def __call__(self):
        return self.t


class FakeStream:
    def __init__(self, signal, clock):
        self.blocks = [signal[i:i + BLOCK] for i in range(0, len(signal) - BLOCK, BLOCK)]
        self.i = 0
        self.clock = clock

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _frames):
        self.clock.advance(BLOCK / SR)
        if self.i >= len(self.blocks):
            # Out of audio: the same thing Ctrl+C does, so main() exits its loop.
            raise KeyboardInterrupt
        block = self.blocks[self.i]
        self.i += 1
        return block.reshape(-1, 1), False


def fake_sounddevice(signal, clock):
    mod = types.ModuleType("sounddevice")
    mod.InputStream = lambda **kw: FakeStream(signal, clock)
    mod.query_devices = lambda *a, **k: {"name": "Fake Mic", "max_input_channels": 1}
    mod.default = types.SimpleNamespace(device=(0, 1))
    return mod


@pytest.fixture
def audio(monkeypatch):
    from clapoff import cli

    def install(signal):
        clock = Clock()
        monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice(signal, clock))
        monkeypatch.setattr(cli, "time", types.SimpleNamespace(monotonic=clock))
    return install


@pytest.fixture
def spy(monkeypatch):
    """Record what the app tried to do, instead of doing it."""
    from clapoff import cli
    done, sent = [], []
    monkeypatch.setattr(cli, "perform",
                        lambda action, command=None, dry_run=False, log=print:
                        done.append((action, command)) or True)

    class Recorder(cli.Notifier):
        def send(self, title, body):
            sent.append((title, body))
            return True

    monkeypatch.setattr(cli, "Notifier", Recorder)
    monkeypatch.setattr(cli, "beep", lambda *a, **k: None)
    monkeypatch.setattr(cli, "key_pressed", lambda: False)
    return done, sent


BASE = ["--no-banner", "--loopback", "off", "--no-profile"]


def test_three_even_claps_shut_the_computer_down(audio, spy, tmp_path):
    from clapoff.cli import main
    done, _ = spy
    audio(even_triple())
    assert main(BASE + ["--countdown", "0.2", "--config", str(tmp_path / "none.json")]) == 0
    assert done == [("shutdown", None)]


def test_the_countdown_reaches_the_desktop(audio, spy, tmp_path):
    """The whole point of notifications: hidden autostart has no console."""
    from clapoff.cli import main
    _, sent = spy
    audio(even_triple())
    main(BASE + ["--countdown", "0.2", "--config", str(tmp_path / "none.json")])
    assert any("shutdown in" in title for title, _ in sent)


def test_listen_mode_shuts_down_absolutely_nothing(audio, spy, tmp_path):
    from clapoff.cli import main
    done, sent = spy
    audio(even_triple())
    main(BASE + ["--listen", "--config", str(tmp_path / "none.json")])
    assert done == []
    assert sent == []


def test_a_quiet_room_does_nothing_at_all(audio, spy, tmp_path):
    from clapoff.cli import main
    done, _ = spy
    audio(room(6.0))
    main(BASE + ["--countdown", "0.2", "--config", str(tmp_path / "none.json")])
    assert done == []


def test_a_syncopated_rhythm_picks_the_other_action(audio, spy, tmp_path):
    """clap ... clap-clap is 2:1, which is lock, and lock has no countdown."""
    from clapoff.cli import main
    done, _ = spy
    sig = np.concatenate([room(1.2), clap(), room(0.55), clap(), room(0.25), clap(), room(2.0)])
    audio(sig)
    main(BASE + ["--config", str(tmp_path / "none.json")])
    assert done == [("lock", None)]


def test_an_unknown_rhythm_does_nothing(audio, spy, tmp_path):
    from clapoff.cli import main
    done, _ = spy
    sig = np.concatenate([room(1.2), clap(), room(0.15), clap(), room(1.1), clap(), room(2.0)])
    audio(sig)
    main(BASE + ["--config", str(tmp_path / "none.json")])
    assert done == []
