"""The bit you actually run."""

import argparse
import collections
import sys
import time

from . import __version__
from .console import beep, drain_keys, key_pressed, say
from .detector import BLOCK, SR, ClapDetector
from .loopback import LoopbackVeto
from .power import shutdown

BANNER = r"""
       _
   ___| | __ _ _ __   ___  / _|/ _|
  / __| |/ _` | '_ \ / _ \| |_| |_
 | (__| | (_| | |_) | (_) |  _|  _|
  \___|_|\__,_| .__/ \___/|_| |_|
              |_|   clap. off. bye.
"""


def build_parser():
    p = argparse.ArgumentParser(
        prog="clapoff",
        description="Turn off your computer by clapping at it.",
    )
    p.add_argument("--claps", type=int, default=3,
                   help="how many claps it takes (default: 3)")
    p.add_argument("--window", type=float, default=2.0,
                   help="seconds to fit them into (default: 2.0)")
    p.add_argument("--countdown", type=float, default=15.0,
                   help="seconds to change your mind (default: 15)")
    p.add_argument("--sensitivity", type=float, default=1.0,
                   help="higher hears more, lower hears less (default: 1.0)")
    p.add_argument("--device", default=None,
                   help="input device index or name; omit for the system default")
    p.add_argument("--list-devices", action="store_true",
                   help="print every microphone this machine admits to having")
    p.add_argument("--listen", action="store_true",
                   help="report claps and shut down absolutely nothing")
    p.add_argument("--dry-run", action="store_true",
                   help="the whole show, including the countdown, minus the shutdown")
    p.add_argument("--loopback", choices=["auto", "off"], default="auto",
                   help="watch your own speakers so music can't trigger it (default: auto)")
    p.add_argument("--loopback-device", default=None,
                   help="name of the output device to watch; omit for the default speaker")
    p.add_argument("--no-banner", action="store_true", help="be boring")
    p.add_argument("--version", action="version", version=f"clapoff {__version__}")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        import sounddevice as sd
    except OSError as exc:      # PortAudio missing - common on bare Linux
        print(f"Couldn't load the audio backend: {exc}\n"
              "On Debian/Ubuntu: sudo apt install libportaudio2", file=sys.stderr)
        return 2

    if args.list_devices:
        print(sd.query_devices())
        return 0

    device = args.device
    if device is not None and device.isdigit():
        device = int(device)

    det = ClapDetector(sensitivity=args.sensitivity)
    veto = LoopbackVeto(device=args.loopback_device)
    if args.loopback == "auto":
        veto.start(time.monotonic)
    else:
        veto.reason = "disabled with --loopback off"
    hits = collections.deque()
    counting_down = False
    deadline = next_tick = 0.0

    if not args.no_banner:
        print(BANNER)

    try:
        info = sd.query_devices(device if device is not None else sd.default.device[0], "input")
    except Exception as exc:
        print(f"No usable microphone ({exc}). Try --list-devices.", file=sys.stderr)
        return 2

    mode = ("LISTEN ONLY - nothing will happen" if args.listen else
            "DRY RUN - nothing will happen, dramatically" if args.dry_run else
            "ARMED - this will really turn your computer off")
    print(f"  mode:    {mode}")
    print(f"  ears:    {info['name']}")
    print(f"  speakers: {veto.status()}")
    print(f"  trigger: {args.claps} claps inside {args.window:g}s")
    print(f"  abort:   {args.countdown:g}s - clap once, or press any key")
    print("  quit:    Ctrl+C\n")

    try:
        with sd.InputStream(samplerate=SR, blocksize=BLOCK, channels=1,
                            dtype="float32", device=device) as stream:
            while True:
                data, _ = stream.read(BLOCK)
                now = time.monotonic()
                event = det.feed(data[:, 0], now)

                if event is not None:
                    kind, rms, hf, spike = event
                    if kind == "clap" and veto.blocks(now):
                        say("ignored - that came out of your own speakers")
                        continue
                    if kind == "clap":
                        hits.append(now)
                        say(f"clap {len(hits)}/{args.claps}   "
                            f"(rms {rms:.4f}  hf {hf:.0%}  spike {spike:.0f}x)")
                    else:
                        if hits:
                            hits.pop()
                        say(f"never mind - that didn't decay, so it was noise (hf {hf:.0%})")

                    if counting_down and kind == "clap":
                        counting_down = False
                        hits.clear()
                        beep(300, 200)
                        say("ABORTED. Carry on.\n")
                        continue

                while hits and now - hits[0] > args.window:
                    hits.popleft()

                if not counting_down and len(hits) >= args.claps:
                    hits.clear()
                    if args.listen:
                        beep(1200, 100)
                        say(f"*** that's {args.claps}. This would have been it. ***\n")
                        continue
                    counting_down = True
                    deadline = now + args.countdown
                    next_tick = now
                    drain_keys()
                    say(f"THAT'S {args.claps}. Powering off in {args.countdown:g}s "
                        "- clap or hit a key if you didn't mean it.")

                if counting_down:
                    if key_pressed():
                        counting_down = False
                        beep(300, 200)
                        say("ABORTED. Carry on.\n")
                        continue
                    if now >= next_tick:
                        left = max(0.0, deadline - now)
                        beep(1000 if left > 5 else 1500, 90)
                        if left > 0.9:
                            say(f"  ...{left:.0f}")
                        next_tick += 1.0
                    if now >= deadline:
                        shutdown(dry_run=args.dry_run, log=say)
                        counting_down = False
    except KeyboardInterrupt:
        print("\nFine. Use the button like everyone else.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
