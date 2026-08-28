"""The bit you actually run."""

import argparse
import collections
import sys
import time

from . import __version__
from .console import beep, drain_keys, key_pressed, say
from .detector import BLOCK, SR, ClapDetector
from .loopback import LoopbackVeto
from .patterns import DEFAULT_TOLERANCE, Pattern, load, match_sequence, write_starter
from .power import perform

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
        description="Turn off your computer by clapping at it. And other rhythms.",
    )
    p.add_argument("--claps", type=int, default=None,
                   help="ignore the pattern file; just N evenly spaced claps to shut down")
    p.add_argument("--settle", type=float, default=0.6,
                   help="silence that ends a rhythm, in seconds (default: 0.6)")
    p.add_argument("--window", type=float, default=3.0,
                   help="longest rhythm to keep in mind, in seconds (default: 3.0)")
    p.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE,
                   help="how sloppy your timing may be, 0-1 (default: 0.30)")
    p.add_argument("--countdown", type=float, default=15.0,
                   help="seconds to change your mind (default: 15)")
    p.add_argument("--sensitivity", type=float, default=1.0,
                   help="higher hears more, lower hears less (default: 1.0)")
    p.add_argument("--device", default=None,
                   help="input device index or name; omit for the system default")
    p.add_argument("--config", default=None, help="path to a patterns file")
    p.add_argument("--patterns", action="store_true",
                   help="print the rhythms it is listening for, then leave")
    p.add_argument("--init-config", action="store_true",
                   help="write a starter pattern file you can edit")
    p.add_argument("--list-devices", action="store_true",
                   help="print every microphone this machine admits to having")
    p.add_argument("--loopback", choices=["auto", "off"], default="auto",
                   help="watch your own speakers so music cannot trigger it (default: auto)")
    p.add_argument("--loopback-device", default=None,
                   help="name of the output device to watch; omit for the default speaker")
    p.add_argument("--listen", action="store_true",
                   help="report rhythms and do absolutely nothing about them")
    p.add_argument("--dry-run", action="store_true",
                   help="the whole show, including the countdown, minus the ending")
    p.add_argument("--no-banner", action="store_true", help="be boring")
    p.add_argument("--version", action="version", version=f"clapoff {__version__}")
    return p


def resolve_patterns(args):
    """Pattern file, or the --claps override, or the built-ins."""
    if args.claps is not None:
        if args.claps < 2:
            raise SystemExit("--claps needs to be at least 2. One clap is just a noise.")
        return [Pattern("shutdown", [1] * (args.claps - 1), "shutdown")], "--claps"
    return load(args.config)


def print_patterns(patterns, source):
    print(f"  patterns from: {source}\n")
    width = max(len(p.name) for p in patterns)
    for p in patterns:
        tail = f" -> {p.command}" if p.action == "command" else ""
        wait = "  (with countdown)" if p.countdown else ""
        print(f"  {p.name:<{width}}  {p.describe():<28} {p.action}{tail}{wait}")
    print()


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.init_config:
        path = write_starter(args.config)
        print(f"Wrote a starter pattern file to {path}. Go and edit it.")
        return 0

    patterns, source = resolve_patterns(args)

    if args.patterns:
        print_patterns(patterns, source)
        return 0

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

    onsets = collections.deque(maxlen=12)
    settle_at = None
    pending = None          # the pattern we are counting down for
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
            "ARMED - this will really do the things below")
    print(f"  mode:     {mode}")
    print(f"  ears:     {info['name']}")
    print(f"  speakers: {veto.status()}")
    print("  quit:     Ctrl+C\n")
    print_patterns(patterns, source)

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
                        if pending is not None:      # a clap mid-countdown means stop
                            pending = None
                            onsets.clear()
                            settle_at = None
                            beep(300, 200)
                            say("ABORTED. Carry on.\n")
                            continue
                        onsets.append(now)
                        settle_at = now + args.settle
                        say(f"clap {len(onsets)}   (rms {rms:.4f}  hf {hf:.0%}  spike {spike:.0f}x)")
                    else:
                        if onsets:
                            onsets.pop()
                        say(f"never mind - that didn't decay, so it was noise (hf {hf:.0%})")

                while onsets and now - onsets[0] > args.window:
                    onsets.popleft()

                # A rhythm ends when you stop clapping, not when a timer says so.
                if settle_at is not None and now >= settle_at:
                    settle_at = None
                    heard = list(onsets)
                    onsets.clear()
                    matched = match_sequence(heard, patterns, args.tolerance)
                    if matched is None:
                        if len(heard) >= 2:
                            say(f"{len(heard)} claps, but not a rhythm I know. Try --patterns.\n")
                        continue
                    if args.listen:
                        beep(1200, 100)
                        say(f'*** that is "{matched.name}" - {matched.action} ***\n')
                        continue
                    if not matched.countdown:
                        perform(matched.action, matched.command, args.dry_run, say)
                        print()
                        continue
                    pending = matched
                    deadline = now + args.countdown
                    next_tick = now
                    drain_keys()
                    say(f'THAT IS "{matched.name}". {matched.action} in {args.countdown:g}s '
                        "- clap or hit a key if you didn't mean it.")

                if pending is not None:
                    if key_pressed():
                        pending = None
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
                        perform(pending.action, pending.command, args.dry_run, say)
                        pending = None
                        print()
    except KeyboardInterrupt:
        print("\nFine. Use the button like everyone else.")
    finally:
        veto.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
