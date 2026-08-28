"""The bit you actually run."""

import argparse
import collections
import statistics
import sys
import time

import numpy as np

from . import __version__
from .console import beep, drain_keys, key_pressed, say
from .detector import BLOCK, SR, ClapDetector
from .doa import DirectionGate, array_report, signature
from . import guards
from .loopback import LoopbackVeto
from .notify import Notifier
from .patterns import DEFAULT_TOLERANCE, Pattern, load, match_sequence, write_starter
from .power import perform
from . import training

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
    p.add_argument("--train", action="store_true",
                   help="learn your clap and your room, and remember it")
    p.add_argument("--profile", default=None, help="path to a trained profile")
    p.add_argument("--no-profile", action="store_true",
                   help="ignore the trained profile and use the stock guesses")
    p.add_argument("--check-array", action="store_true",
                   help="find out whether your mic is a real array or four copies of one")
    p.add_argument("--train-direction", action="store_true",
                   help="learn where you sit, and ignore claps from anywhere else")
    p.add_argument("--direction-tolerance", type=float, default=2.0,
                   help="how far you may drift, in samples (default: 2)")
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
    p.add_argument("--guards", choices=["auto", "off"], default="auto",
                   help="refuse to end your session mid-call or mid-game (default: auto)")
    p.add_argument("--notify", choices=["auto", "off"], default="auto",
                   help="put the countdown on the desktop too (default: auto)")
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


def open_mic(sd, device, channels=1):
    return sd.InputStream(samplerate=SR, blocksize=BLOCK, channels=channels,
                          dtype="float32", device=device)


def channel_count(sd, device):
    try:
        info = sd.query_devices(device if device is not None else sd.default.device[0], "input")
        return max(1, min(int(info["max_input_channels"]), 4))
    except Exception:
        return 1


def run_check_array(sd, device):
    """Tell the truth about the microphone before anyone builds on top of it."""
    channels = channel_count(sd, device)
    if channels < 2:
        print("One channel. Nothing to compare it against, so no direction. That's fine.")
        return 0
    print(f"Listening on {channels} channels for two seconds. Make some noise.\n")
    frames = []
    with open_mic(sd, device, channels) as stream:
        for _ in range(int(2.0 * SR / BLOCK)):
            data, _ = stream.read(BLOCK)
            frames.append(data)
    report = array_report(np.concatenate(frames))
    for entry in report["channels"]:
        corr = f"  corr vs ch0 {entry['corr']:+.4f}" if "corr" in entry else ""
        print(f"  ch{entry['channel']}  rms {entry['rms']:.6f}  {entry['verdict']}{corr}")
    print()
    if report["usable"]:
        print(f"Usable: {report['reason']}. Run clapoff --train-direction.")
        return 0
    print(f"Not usable: {report['reason']}.")
    print("Direction gating will stay off. Everything else works exactly as before.")
    return 0


def run_train_direction(args, sd, device):
    """Learn the delay fingerprint of claps from where you actually sit."""
    channels = channel_count(sd, device)
    if channels < 2:
        print("This microphone has one channel. There is no direction to learn.")
        return 1

    print(f"Clap six times from where you normally sit. Listening on {channels} channels.\n")
    det = ClapDetector(sensitivity=2.0)
    recent = collections.deque(maxlen=8)
    prints = []
    with open_mic(sd, device, channels) as stream:
        start = time.monotonic()
        while len(prints) < 6 and time.monotonic() - start < 90:
            data, _ = stream.read(BLOCK)
            recent.append(data)
            event = det.feed(data[:, 0], time.monotonic())
            if event is not None and event[0] == "clap" and len(recent) == recent.maxlen:
                prints.append(signature(np.concatenate(recent)))
                print(f"  got one - {len(prints)}/6  {prints[-1]}")

    if len(prints) < 3:
        print(f"\nOnly heard {len(prints)}. Try clapoff --listen first.")
        return 1
    reference = [round(statistics.median(p[j] for p in prints), 2)
                 for j in range(len(prints[0]))]
    check = array_report(np.concatenate(recent))
    if not check["usable"]:
        print(f"\nHeard you fine, but: {check['reason']}.")
        print("Refusing to save a direction that would be built on noise.")
        return 1
    path = training.update({"direction": reference,
                            "direction_tolerance": args.direction_tolerance}, args.profile)
    print(f"\nYour direction is {reference}. Saved to {path}.")
    return 0


def run_training(args, sd, device):
    """Ten claps for the thresholds, one rhythm for the timing."""
    print("Right. Two short phases, then it stops guessing about you.\n")
    try:
        with open_mic(sd, device) as stream:
            def read():
                data, _ = stream.read(BLOCK)
                return data[:, 0]

            print("Phase 1 of 2 - clap ten times, normally, with a beat between each.")
            samples, _ = training.collect(read, time.monotonic, want=10, timeout=90)
            if len(samples) < training.MIN_SAMPLES:
                print(f"\nOnly heard {len(samples)}. Either the mic is wrong or you gave up. "
                      "Try clapoff --listen first.")
                return 1

            print("\nPhase 2 of 2 - clap an even three, clap-clap-clap, three times over.")
            _, times = training.collect(read, time.monotonic, want=9, timeout=90)
    except Exception as exc:
        print(f"Training failed to open the microphone ({exc}).", file=sys.stderr)
        return 2

    gaps = [b - a for a, b in zip(times, times[1:]) if 0.10 <= b - a <= 1.50]
    profile = training.fit(samples, gaps)
    path = training.save(profile, args.profile)

    print(f"\nLearned from {profile['samples']} claps and {len(gaps)} gaps:")
    print(f"  brightness floor  hf_min    {profile['hf_min']}")
    print(f"  spike threshold   ratio     {profile['ratio']}x over your background")
    print(f"  quietest allowed  abs_min   {profile['abs_min']}")
    if "tolerance" in profile:
        print(f"  rhythm sloppiness tolerance {profile['tolerance']}")
    print(f"\nSaved to {path}. It'll be used automatically from now on.")
    return 0


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

    if args.check_array:
        return run_check_array(sd, device)

    if args.train_direction:
        return run_train_direction(args, sd, device)

    if args.train:
        return run_training(args, sd, device)

    if args.no_profile:
        learned, profile_note = None, "ignored with --no-profile"
    else:
        learned, profile_note = training.load(args.profile)
    settings = dict(learned or {})
    # An explicit --tolerance beats a learned one; otherwise the learned one wins.
    tolerance = settings.pop("tolerance", args.tolerance)
    if args.tolerance != DEFAULT_TOLERANCE:
        tolerance = args.tolerance
    gate = DirectionGate(settings.pop("direction", None), args.direction_tolerance)
    channels = channel_count(sd, device) if gate.active else 1

    det = ClapDetector(sensitivity=args.sensitivity, **settings)
    notifier = Notifier(enabled=args.notify == "auto" and not args.listen)
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
    print(f"  profile:  {profile_note}")
    print(f"  direction: {gate.status()}")
    print(f"  notices:  {notifier.status()}")
    print(f"  guards:   {guards.status() if args.guards == 'auto' else 'off'}")
    print("  quit:     Ctrl+C\n")
    print_patterns(patterns, source)

    try:
        recent = collections.deque(maxlen=8)     # ~128 ms of multichannel history
        with open_mic(sd, device, channels) as stream:
            while True:
                data, _ = stream.read(BLOCK)
                now = time.monotonic()
                if gate.active:
                    recent.append(data)
                event = det.feed(data[:, 0], now)

                if event is not None:
                    kind, rms, hf, spike = event
                    if kind == "clap" and veto.blocks(now):
                        say("ignored - that came out of your own speakers")
                        continue
                    if (kind == "clap" and gate.active
                            and len(recent) == recent.maxlen
                            and not gate.accepts(signature(np.concatenate(recent)))):
                        say("ignored - that clap came from somewhere else")
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
                    matched = match_sequence(heard, patterns, tolerance)
                    if matched is None:
                        if len(heard) >= 2:
                            say(f"{len(heard)} claps, but not a rhythm I know. Try --patterns.\n")
                        continue
                    if args.listen:
                        beep(1200, 100)
                        say(f'*** that is "{matched.name}" - {matched.action} ***\n')
                        continue
                    # Session-ending actions ask the desktop's permission first.
                    excuse = (guards.why_not_now()
                              if args.guards == "auto" and matched.countdown else None)
                    if excuse:
                        beep(300, 200)
                        say(f"not now - {excuse}.")
                        say("(clapoff --guards off if you disagree)\n")
                        notifier.send("clapoff: not now", excuse)
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
                    notifier.send(
                        f"clapoff: {matched.action} in {args.countdown:g}s",
                        "Clap once to cancel. Hidden mode has no keyboard.")

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
