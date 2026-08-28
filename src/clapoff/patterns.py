"""Rhythm as a keyspace.

"Three claps in two seconds" is one bit of information, which is a waste of a
perfectly good microphone. Match on the *ratios between* the gaps instead and
you get as many commands as you can be bothered to remember:

    clap-clap-clap        1:1     even            -> shutdown
    clap-clap ... clap    1:2     hurry then wait -> sleep
    clap ... clap-clap    2:1     wait then hurry -> lock

Ratios are scale-free, so it works whether you clap it fast or slow. This is
also the cheapest false-positive fix available: a syncopated 1:2 is much harder
for a passing drum fill to hit by accident than "any three onsets in a row".
"""

import json
import os
import pathlib

# Actions that end your session get a countdown. Locking the screen does not,
# because the worst case is you press a key.
NEEDS_CONFIRMING = {"shutdown", "sleep", "reboot"}

DEFAULT_TOLERANCE = 0.30


class Pattern:
    """A rhythm, and what to do when someone claps it."""

    def __init__(self, name, rhythm, action="shutdown", command=None, countdown=None):
        self.name = name
        self.rhythm = list(rhythm)
        if len(self.rhythm) < 1:
            raise ValueError(f"pattern {name!r} needs at least one interval (two claps)")
        if any(r <= 0 for r in self.rhythm):
            raise ValueError(f"pattern {name!r} has a non-positive interval")
        self.action = action
        self.command = command
        self.countdown = NEEDS_CONFIRMING.__contains__(action) if countdown is None else countdown

    @property
    def claps(self):
        return len(self.rhythm) + 1

    def describe(self):
        """A rhythm you can read out loud, e.g. 'clap-clap ... clap'."""
        smallest = min(self.rhythm)
        parts = ["clap"]
        for gap in self.rhythm:
            parts.append(" ... " if gap > smallest * 1.5 else "-")
            parts.append("clap")
        return "".join(parts)

    def __repr__(self):
        return f"Pattern({self.name!r}, {self.rhythm!r}, {self.action!r})"


DEFAULTS = [
    Pattern("shutdown", [1, 1], "shutdown"),
    Pattern("sleep", [1, 2], "sleep"),
    Pattern("lock", [2, 1], "lock"),
]


def intervals(times):
    """Gaps between consecutive claps."""
    return [b - a for a, b in zip(times, times[1:])]


def matches(gaps, rhythm, tolerance=DEFAULT_TOLERANCE):
    """Does this sequence of gaps have the shape of this rhythm?

    Scaled by total duration rather than by the first gap, so one rushed opening
    clap doesn't throw off everything after it.
    """
    if len(gaps) != len(rhythm) or not gaps:
        return False
    scale = sum(gaps) / sum(rhythm)
    return all(abs(g - r * scale) <= tolerance * r * scale for g, r in zip(gaps, rhythm))


def match_sequence(times, patterns, tolerance=DEFAULT_TOLERANCE,
                   min_gap=0.10, max_gap=1.5):
    """Find the pattern someone just clapped, or None.

    Gaps outside [min_gap, max_gap] aren't rhythm, they're two separate events
    that happen to be adjacent.
    """
    if len(times) < 2:
        return None
    gaps = intervals(times)
    if any(g < min_gap or g > max_gap for g in gaps):
        return None
    for pattern in patterns:
        if matches(gaps, pattern.rhythm, tolerance):
            return pattern
    return None


def config_path():
    """Where the config lives. Respects XDG, because some of us have standards."""
    override = os.environ.get("CLAPOFF_CONFIG")
    if override:
        return pathlib.Path(override)
    if os.name == "nt":
        base = os.environ.get("APPDATA") or pathlib.Path.home() / "AppData" / "Roaming"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config"
    return pathlib.Path(base) / "clapoff" / "patterns.json"


def parse_rhythm(raw):
    """Accept [1, 2] or "1,2" or "1:2", because people type what they think of."""
    if isinstance(raw, (list, tuple)):
        return [float(x) for x in raw]
    return [float(x) for x in str(raw).replace(":", ",").split(",") if x.strip()]


def load(path=None):
    """Read patterns from disk. Returns (patterns, note-for-the-human)."""
    path = pathlib.Path(path) if path else config_path()
    if not path.exists():
        return list(DEFAULTS), "built-in"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        patterns = [
            Pattern(
                name=entry.get("name", "unnamed"),
                rhythm=parse_rhythm(entry["rhythm"]),
                action=entry.get("action", "command" if entry.get("command") else "shutdown"),
                command=entry.get("command"),
                countdown=entry.get("countdown"),
            )
            for entry in raw["patterns"]
        ]
        if not patterns:
            return list(DEFAULTS), f"{path} had no patterns, using built-ins"
        return patterns, str(path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return list(DEFAULTS), f"{path} is unreadable ({exc}), using built-ins"


STARTER_CONFIG = {
    "patterns": [
        {"name": "shutdown", "rhythm": "1,1", "action": "shutdown"},
        {"name": "sleep", "rhythm": "1,2", "action": "sleep"},
        {"name": "lock", "rhythm": "2,1", "action": "lock"},
        {"name": "say hello", "rhythm": "1,1,1", "action": "command",
         "command": "echo you clapped four times"},
    ]
}


def write_starter(path=None):
    path = pathlib.Path(path) if path else config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(STARTER_CONFIG, indent=2) + "\n", encoding="utf-8")
    return path
