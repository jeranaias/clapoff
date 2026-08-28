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


# --- the mic-startup bug -----------------------------------------------------

def test_digital_silence_at_startup_does_not_fire():
    """Regression: a stream that opens with true zeros used to make the rolling
    median ~0, so the first ordinary room noise read as a 300,000x spike and the
    detector fired twice at an empty room."""
    sig = np.concatenate([
        np.zeros(int(SR * 1.0), dtype=np.float32),   # mic hasn't woken up yet
        room_tone(3.0, level=0.015),                 # a normal, boring room
    ])
    assert count(sig)[0] == 0


def test_real_claps_still_fire_after_a_silent_start():
    """...and the floor must not deafen it once the room is actually running."""
    sig = np.concatenate([
        np.zeros(int(SR * 0.5), dtype=np.float32),
        room_tone(1.0, level=0.015), clap(), room_tone(0.4, level=0.015),
        clap(), room_tone(0.4, level=0.015), clap(), room_tone(0.5, level=0.015),
    ])
    assert count(sig)[0] == 3


# --- the speaker veto --------------------------------------------------------

class TestSpeakerActivity:
    """The bookkeeping half of the loopback veto, which is the testable half."""

    def test_a_fresh_pop_blocks(self):
        from clapoff.loopback import SpeakerActivity
        a = SpeakerActivity(hold=0.25)
        a.mark(10.0)
        assert a.blocks(10.05) is True

    def test_an_old_pop_does_not(self):
        from clapoff.loopback import SpeakerActivity
        a = SpeakerActivity(hold=0.25)
        a.mark(10.0)
        assert a.blocks(10.5) is False

    def test_the_future_does_not_block(self):
        from clapoff.loopback import SpeakerActivity
        a = SpeakerActivity(hold=0.25)
        a.mark(10.0)
        assert a.blocks(9.9) is False

    def test_silence_blocks_nothing(self):
        from clapoff.loopback import SpeakerActivity
        assert SpeakerActivity().blocks(1.0) is False


class TestLoopbackVeto:
    def test_it_fails_politely_without_a_device(self):
        """No speakers, no soundcard, no problem - it must not take the app down."""
        from clapoff.loopback import LoopbackVeto
        v = LoopbackVeto(device="a device that does not exist anywhere")
        v.start(lambda: 0.0)
        assert v.available is False
        assert v.blocks(1.0) is False
        assert "off - " in v.status()

    def test_an_unavailable_veto_never_vetoes(self):
        from clapoff.loopback import LoopbackVeto
        v = LoopbackVeto()
        v.activity.mark(10.0)          # even with a pop on the books
        assert v.blocks(10.05) is False  # ...it's off, so it stays out of the way


# --- rhythm patterns ---------------------------------------------------------

class TestRhythmMatching:
    """Ratios, not absolute times. Clap it fast or slow, same pattern."""

    def test_even_triple_matches_1_1(self):
        from clapoff.patterns import matches
        assert matches([0.30, 0.30], [1, 1]) is True

    def test_the_same_rhythm_clapped_slowly_still_matches(self):
        from clapoff.patterns import matches
        assert matches([0.90, 0.90], [1, 1]) is True

    def test_syncopation_is_a_different_key(self):
        from clapoff.patterns import matches
        assert matches([0.30, 0.60], [1, 2]) is True
        assert matches([0.30, 0.60], [1, 1]) is False
        assert matches([0.30, 0.30], [1, 2]) is False

    def test_reversed_syncopation_is_yet_another(self):
        from clapoff.patterns import matches
        assert matches([0.60, 0.30], [2, 1]) is True
        assert matches([0.60, 0.30], [1, 2]) is False

    def test_human_sloppiness_is_forgiven(self):
        from clapoff.patterns import matches
        assert matches([0.28, 0.33], [1, 1]) is True      # nobody is a metronome

    def test_wrong_number_of_claps_never_matches(self):
        from clapoff.patterns import matches
        assert matches([0.3, 0.3, 0.3], [1, 1]) is False
        assert matches([], [1, 1]) is False


class TestMatchSequence:
    def test_it_picks_the_right_pattern_out_of_the_set(self):
        from clapoff.patterns import DEFAULTS, match_sequence
        assert match_sequence([0.0, 0.3, 0.6], DEFAULTS).name == "shutdown"
        assert match_sequence([0.0, 0.3, 0.9], DEFAULTS).name == "sleep"
        assert match_sequence([0.0, 0.6, 0.9], DEFAULTS).name == "lock"

    def test_one_clap_is_not_a_rhythm(self):
        from clapoff.patterns import DEFAULTS, match_sequence
        assert match_sequence([0.0], DEFAULTS) is None
        assert match_sequence([], DEFAULTS) is None

    def test_gaps_that_are_too_long_are_two_events_not_a_rhythm(self):
        from clapoff.patterns import DEFAULTS, match_sequence
        assert match_sequence([0.0, 4.0, 8.0], DEFAULTS) is None

    def test_gaps_that_are_too_short_are_one_clap_echoing(self):
        from clapoff.patterns import DEFAULTS, match_sequence
        assert match_sequence([0.0, 0.02, 0.04], DEFAULTS) is None

    def test_an_unknown_rhythm_matches_nothing(self):
        from clapoff.patterns import DEFAULTS, match_sequence
        assert match_sequence([0.0, 0.2, 1.0], DEFAULTS) is None


class TestPatternConfig:
    def test_missing_config_falls_back_to_built_ins(self, tmp_path):
        from clapoff.patterns import DEFAULTS, load
        patterns, source = load(tmp_path / "nope.json")
        assert [p.name for p in patterns] == [p.name for p in DEFAULTS]
        assert source == "built-in"

    def test_a_written_starter_reads_back(self, tmp_path):
        from clapoff.patterns import load, write_starter
        path = write_starter(tmp_path / "patterns.json")
        patterns, source = load(path)
        assert "shutdown" in [p.name for p in patterns]
        assert source == str(path)

    def test_garbage_config_does_not_take_the_app_down(self, tmp_path):
        from clapoff.patterns import load
        bad = tmp_path / "bad.json"
        bad.write_text("{ this is not json", encoding="utf-8")
        patterns, source = load(bad)
        assert len(patterns) == 3            # quietly back to the built-ins
        assert "unreadable" in source

    def test_rhythm_accepts_however_you_felt_like_typing_it(self):
        from clapoff.patterns import parse_rhythm
        assert parse_rhythm("1,2") == [1.0, 2.0]
        assert parse_rhythm("1:2") == [1.0, 2.0]
        assert parse_rhythm([1, 2]) == [1.0, 2.0]

    def test_destructive_actions_get_a_countdown_and_lock_does_not(self):
        from clapoff.patterns import Pattern
        assert Pattern("a", [1, 1], "shutdown").countdown is True
        assert Pattern("b", [1, 1], "sleep").countdown is True
        assert Pattern("c", [1, 1], "lock").countdown is False

    def test_a_pattern_needs_at_least_two_claps(self):
        import pytest as _pytest
        from clapoff.patterns import Pattern
        with _pytest.raises(ValueError):
            Pattern("nope", [], "shutdown")


class TestPowerActions:
    def test_every_platform_knows_every_action(self):
        from clapoff.power import COMMANDS
        for system, actions in COMMANDS.items():
            assert set(actions) == {"shutdown", "reboot", "sleep", "lock"}, system

    def test_dry_run_never_actually_runs_anything(self):
        from clapoff.power import perform
        lines = []
        assert perform("shutdown", dry_run=True, log=lines.append) is True
        assert "DRY RUN" in lines[0]

    def test_a_command_pattern_with_no_command_complains(self):
        from clapoff.power import perform
        lines = []
        assert perform("command", None, dry_run=True, log=lines.append) is False
