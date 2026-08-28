"""Learning your clap, instead of guessing at everybody's.

The stock thresholds describe a generic clap in a generic room, which is to say
nobody's clap in nobody's room. Ten claps is enough to replace every guess with
a measurement: how bright your hands actually are, how far above your own
background they land, and how sloppy your sense of rhythm really is.

The capture loop takes a `read_block` callable rather than opening a stream, so
the whole thing can be trained on synthetic audio in a test.
"""

import json
import pathlib
import statistics

from .detector import ClapDetector
from .patterns import config_path

FIELDS = ("hf_min", "ratio", "abs_min", "tolerance")
LIST_FIELDS = ("direction",)
MIN_SAMPLES = 5


def profile_path(path=None):
    if path:
        return pathlib.Path(path)
    return config_path().with_name("profile.json")


def percentile(values, q):
    """Small, dependency-free, and good enough for ten numbers."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("no values")
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def winnow(samples):
    """Throw out the things that were plainly not one of your claps.

    Training listens permissively on purpose - a missed example costs more than
    a spurious one. But that also means a chair scrape can sneak into the set,
    and since the thresholds are anchored on the *weakest* sample, one piece of
    junk would drag the whole bar down and leave you with a hair trigger. So
    anything far below the median of the batch is not one of yours.
    """
    if len(samples) < MIN_SAMPLES:
        return samples
    mid_hf = statistics.median(s[1] for s in samples)
    mid_spike = statistics.median(s[2] for s in samples)
    kept = [s for s in samples if s[1] >= 0.60 * mid_hf and s[2] >= 0.25 * mid_spike]
    return kept if len(kept) >= MIN_SAMPLES else samples


def fit(samples, gaps=None):
    """Turn observed claps into detector settings.

    Anchored on the *tenth* percentile rather than the mean: the threshold has to
    admit your weakest clap, not your average one, or half of them stop working.
    Each is then given headroom, because the day you train it is not the only day
    you will use it.
    """
    if len(samples) < MIN_SAMPLES:
        raise ValueError(f"need at least {MIN_SAMPLES} claps, got {len(samples)}")
    kept = winnow(samples)
    rms = [s[0] for s in kept]
    hf = [s[1] for s in kept]
    spike = [s[2] for s in kept]

    profile = {
        "hf_min": round(max(0.15, min(0.60, percentile(hf, 0.10) * 0.80)), 3),
        "ratio": round(max(4.0, percentile(spike, 0.10) * 0.60), 2),
        "abs_min": round(max(0.002, min(0.050, percentile(rms, 0.10) * 0.50)), 5),
        "samples": len(kept),
        "discarded": len(samples) - len(kept),
    }
    if gaps:
        # How far off an even beat you actually are, plus a bit of grace.
        even = statistics.fmean(gaps)
        drift = max(abs(g - even) / even for g in gaps) if even > 0 else 0.0
        profile["tolerance"] = round(max(0.15, min(0.45, drift * 1.5)), 3)
    return profile


def collect(read_block, clock, want=10, timeout=60.0, log=print, sensitivity=2.0):
    """Listen for `want` claps. Returns (feature samples, clap times).

    Deliberately permissive - we're gathering examples, not guarding a power
    button, and a missed sample costs more here than a spurious one.
    """
    det = ClapDetector(sensitivity=sensitivity)
    samples, times = [], []
    start = now = clock()
    while len(samples) < want and now - start < timeout:
        block = read_block()
        if block is None:
            break
        now = clock()          # once per block, so a stream's own clock works too
        event = det.feed(block, now)
        if event is not None and event[0] == "clap":
            samples.append((event[1], event[2], event[3]))
            times.append(now)
            log(f"  got one - {len(samples)}/{want}")
    return samples, times


def save(profile, path=None):
    path = profile_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    return path


def update(changes, path=None):
    """Merge into whatever profile is already on disk, rather than flattening it."""
    path = profile_path(path)
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
    existing.update(changes)
    return save(existing, path)


def load(path=None):
    """Read a profile. Returns (settings-or-None, note-for-the-human)."""
    path = profile_path(path)
    if not path.exists():
        return None, "untrained (run: clapoff --train)"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        settings = {k: float(data[k]) for k in FIELDS if k in data}
        for k in LIST_FIELDS:
            if isinstance(data.get(k), list):
                settings[k] = [float(v) for v in data[k]]
        if not settings:
            return None, f"{path} has nothing usable in it"
        note = f"trained on {data.get('samples', '?')} claps"
        if "direction" in settings:
            note += ", plus a direction"
        return settings, note
    except (OSError, ValueError, TypeError) as exc:
        return None, f"{path} is unreadable ({exc})"
