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


# --- learning your clap ------------------------------------------------------

class TestPercentile:
    def test_it_agrees_with_arithmetic(self):
        from clapoff.training import percentile
        assert percentile([1, 2, 3, 4, 5], 0.0) == 1
        assert percentile([1, 2, 3, 4, 5], 1.0) == 5
        assert percentile([1, 2, 3, 4, 5], 0.5) == 3

    def test_one_value_is_its_own_percentile(self):
        from clapoff.training import percentile
        assert percentile([7], 0.1) == 7


class TestFit:
    samples = [(0.05, 0.70, 30.0), (0.04, 0.65, 25.0), (0.06, 0.75, 40.0),
               (0.03, 0.60, 20.0), (0.05, 0.68, 28.0), (0.04, 0.72, 33.0)]

    def test_it_refuses_to_fit_three_claps(self):
        import pytest as _pytest
        from clapoff.training import fit
        with _pytest.raises(ValueError):
            fit(self.samples[:3])

    def test_thresholds_land_below_the_weakest_clap(self):
        """If the bar lands on the average, half your claps stop working."""
        from clapoff.training import fit
        p = fit(self.samples)
        assert p["hf_min"] < min(s[1] for s in self.samples)
        assert p["ratio"] < min(s[2] for s in self.samples)
        assert p["abs_min"] < min(s[0] for s in self.samples)

    def test_it_never_returns_something_absurd(self):
        from clapoff.training import fit
        wild = [(9.0, 1.0, 9e9)] * 6
        p = fit(wild)
        assert 0.15 <= p["hf_min"] <= 0.60
        assert 0.002 <= p["abs_min"] <= 0.050
        assert p["ratio"] >= 4.0

    def test_a_steady_clapper_earns_a_tight_tolerance(self):
        from clapoff.training import fit
        steady = fit(self.samples, gaps=[0.30, 0.30, 0.31, 0.30])
        sloppy = fit(self.samples, gaps=[0.20, 0.40, 0.25, 0.45])
        assert steady["tolerance"] < sloppy["tolerance"]

    def test_no_rhythm_means_no_learned_tolerance(self):
        from clapoff.training import fit
        assert "tolerance" not in fit(self.samples)


class TestCollect:
    def test_it_gathers_claps_from_a_fed_stream(self):
        """The capture loop takes a reader, so it trains fine on fake audio."""
        from clapoff.training import collect
        sig = np.concatenate([room_tone(1.0)] + [
            np.concatenate([clap(0.4), room_tone(0.35)]) for _ in range(8)])
        blocks = [sig[i:i + BLOCK] for i in range(0, len(sig) - BLOCK, BLOCK)]
        state = {"i": 0}

        def read():
            if state["i"] >= len(blocks):
                return None
            state["i"] += 1
            return blocks[state["i"] - 1]

        def clock():                      # time derived from stream position
            return state["i"] * (BLOCK / SR)

        samples, times = collect(read, clock, want=6, log=lambda *_: None)
        assert len(samples) >= 5
        assert len(times) == len(samples)
        assert all(0.0 < hf <= 1.0 for _, hf, _ in samples)

    def test_it_gives_up_when_the_stream_ends(self):
        from clapoff.training import collect
        samples, _ = collect(lambda: None, lambda: 0.0, want=10, log=lambda *_: None)
        assert samples == []


class TestProfileFile:
    def test_save_then_load_round_trips(self, tmp_path):
        from clapoff.training import load, save
        path = save({"hf_min": 0.4, "ratio": 12.0, "abs_min": 0.01, "samples": 10},
                    tmp_path / "p.json")
        settings, note = load(path)
        assert settings == {"hf_min": 0.4, "ratio": 12.0, "abs_min": 0.01}
        assert "10 claps" in note

    def test_no_profile_says_so_politely(self, tmp_path):
        from clapoff.training import load
        settings, note = load(tmp_path / "absent.json")
        assert settings is None and "untrained" in note

    def test_garbage_profile_does_not_take_the_app_down(self, tmp_path):
        from clapoff.training import load
        bad = tmp_path / "bad.json"
        bad.write_text("not json at all", encoding="utf-8")
        settings, note = load(bad)
        assert settings is None and "unreadable" in note


class TestProfileActuallyChangesBehaviour:
    def test_a_learned_profile_can_hear_a_clap_the_defaults_miss(self):
        """A soft clap in a bright room: stock thresholds reject it, yours don't."""
        soft = np.concatenate([room_tone(1.0), clap(0.02), room_tone(0.5)])
        stock = count(soft)[0]
        det = ClapDetector(hf_min=0.20, ratio=4.0, abs_min=0.002)
        trained = 0
        now = 0.0
        for i in range(0, len(soft) - BLOCK, BLOCK):
            now += BLOCK / SR
            ev = det.feed(soft[i:i + BLOCK], now)
            if ev and ev[0] == "clap":
                trained += 1
        assert trained > stock


class TestWinnow:
    """Training listens permissively, so junk gets in. It must not survive."""

    good = [(0.05, 0.70, 30.0), (0.04, 0.65, 25.0), (0.06, 0.75, 40.0),
            (0.03, 0.60, 20.0), (0.05, 0.68, 28.0), (0.04, 0.72, 33.0)]
    junk = [(0.009, 0.28, 5.0), (0.010, 0.30, 6.0)]     # a chair, a cough

    def test_junk_is_dropped(self):
        from clapoff.training import winnow
        assert len(winnow(self.good + self.junk)) == len(self.good)

    def test_good_claps_all_survive(self):
        from clapoff.training import winnow
        assert len(winnow(self.good)) == len(self.good)

    def test_a_polluted_batch_fits_almost_the_same_as_a_clean_one(self):
        from clapoff.training import fit
        clean = fit(self.good)
        dirty = fit(self.good + self.junk)
        assert dirty["hf_min"] == clean["hf_min"]
        assert dirty["ratio"] == clean["ratio"]
        assert dirty["discarded"] == 2

    def test_it_refuses_to_throw_away_everything(self):
        """If the whole batch looks odd, that's your clap, not an outlier."""
        from clapoff.training import winnow
        weird = [(0.01, 0.30, 5.0)] * 6
        assert len(winnow(weird)) == 6
