"""Whatever you chose in the setup window, remembered.

The command line has a flag for everything, which is wonderful if you like flags
and useless if you don't. This is where the setup window writes your answers so
that plain `clapoff`, with no arguments at all, does the thing you asked for.

Flags still win. If you pass one explicitly it overrides what's saved here.
"""

import json
import pathlib

from .patterns import config_path

DEFAULTS = {
    "device": None,          # None means "whatever the system calls default"
    "sensitivity": 1.0,
    "countdown": 15.0,
    "guards": "auto",
    "notify": "auto",
    "loopback": "auto",
    "tray": False,
}


def settings_path(path=None):
    if path:
        return pathlib.Path(path)
    return config_path().with_name("settings.json")


def load(path=None):
    """Saved answers merged over the defaults. Never raises, never blocks startup."""
    values = dict(DEFAULTS)
    target = settings_path(path)
    if not target.exists():
        return values
    try:
        saved = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return values          # a corrupt settings file is not worth a crash
    if isinstance(saved, dict):
        for key in DEFAULTS:
            if key in saved:
                values[key] = saved[key]
    return values


def save(values, path=None):
    target = settings_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: values[k] for k in DEFAULTS if k in values}
    target.write_text(json.dumps(keep, indent=2) + "\n", encoding="utf-8")
    return target
