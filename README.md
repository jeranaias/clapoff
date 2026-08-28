<h1 align="center">👏 clapoff</h1>

<p align="center">
  <b>Turn off your computer by clapping at it.</b><br>
  <sub>That's the whole repo. You clap. It dies. We're done here.</sub>
</p>

<p align="center">
  <a href="https://github.com/jeranaias/clapoff/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/jeranaias/clapoff/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue.svg">
  <img alt="Python" src="https://img.shields.io/badge/python-3.9%2B-blue.svg">
  <img alt="Platforms" src="https://img.shields.io/badge/platform-windows%20%7C%20macos%20%7C%20linux-lightgrey.svg">
  <img alt="Works on my machine" src="https://img.shields.io/badge/works%20on-my%20machine-success.svg">
</p>

---

## Why

The power button is four feet away and I am not an animal.

## What it looks like

```
       _
   ___| | __ _ _ __   ___  / _|/ _|
  / __| |/ _` | '_ \ / _ \| |_| |_
 | (__| | (_| | |_) | (_) |  _|  _|
  \___|_|\__,_| .__/ \___/|_| |_|
              |_|   clap. off. bye.

  mode:     ARMED - this will really do the things below
  ears:     Microphone Array (Intel Smart Sound)
  speakers: watching "Speakers (Realtek Audio)"
  quit:     Ctrl+C

  patterns from: built-in

  shutdown  clap-clap-clap               shutdown  (with countdown)
  sleep     clap-clap ... clap           sleep  (with countdown)
  lock      clap ... clap-clap           lock

[14:32:07] clap 1   (rms 0.0412  hf 71%  spike 34x)
[14:32:07] clap 2   (rms 0.0388  hf 68%  spike 29x)
[14:32:08] clap 3   (rms 0.0455  hf 74%  spike 41x)
[14:32:08] THAT IS "shutdown". shutdown in 15s - clap or hit a key if you didn't mean it.
[14:32:08]   ...15
[14:32:09]   ...14
[14:32:10]   ...13
```

## Install

```bash
pip install git+https://github.com/jeranaias/clapoff
```

On bare Linux you may also need the audio backend, because Linux:

```bash
sudo apt install libportaudio2
```

## Use it

**Start here.** This mode cannot turn anything off, no matter how hard you clap:

```bash
clapoff --listen
```

Clap three times. Watch it count. Bond with it. Then, when you're ready to hand a
microphone the authority to end your session:

```bash
clapoff
```

Three claps inside two seconds starts a fifteen-second countdown with a beep every
second. **One clap cancels it.** So does any key. This is deliberate — the entire
point is that you are not at the keyboard, so the abort can't require the keyboard.

```bash
clapoff --dry-run          # the full performance, minus the ending
clapoff --patterns         # what rhythms am I listening for again
clapoff --claps 4          # forget rhythms, just make it four claps
clapoff --sensitivity 1.5  # it's not hearing you
clapoff --sensitivity 0.6  # it's hearing things that aren't there
clapoff --list-devices     # every mic your machine admits to having
clapoff --device 3         # use that one instead
```

## Rhythm is a keyspace

"Three claps in two seconds" is one bit of information, which is a waste of a
perfectly good microphone. clapoff matches on the **ratios between the gaps**, so you
get as many commands as you can be bothered to remember:

| You clap | Ratio | It does |
| --- | --- | --- |
| `clap-clap-clap` | `1:1` | shutdown |
| `clap-clap ... clap` | `1:2` | sleep |
| `clap ... clap-clap` | `2:1` | lock the screen |

Ratios are scale-free, so it works whether you clap it fast or slow — only the shape
matters, and you're allowed to be about 30% sloppy about it (`--tolerance`). A rhythm
ends when you stop clapping, not when a timer runs out, so `1:1` never fires early and
steals a clap from `1:1:1`.

This is also the cheapest false-positive fix going. A syncopated `1:2` is a much harder
accident for a passing drum fill than "any three onsets in a row."

Add your own:

```bash
clapoff --init-config      # writes a starter file, tells you where
```

```json
{
  "patterns": [
    { "name": "shutdown",  "rhythm": "1,1",   "action": "shutdown" },
    { "name": "lock",      "rhythm": "2,1",   "action": "lock" },
    { "name": "pause",     "rhythm": "1,1,1", "action": "command",
      "command": "playerctl play-pause" }
  ]
}
```

Actions are `shutdown`, `reboot`, `sleep`, `lock`, or `command` for anything else.
The ones that end your session get the countdown; locking the screen doesn't, because
the worst case there is that you press a key. Override per pattern with
`"countdown": true`.

## Teaching it your clap

The stock thresholds describe a generic clap in a generic room, which is to say
nobody's clap in nobody's room. Two minutes fixes that:

```bash
clapoff --train
```

Phase one: clap ten times. Phase two: clap an even `clap-clap-clap` three times over.
It measures how bright your hands actually are, how far above *your* background they
land, and how sloppy your sense of rhythm honestly is — then writes all of that to a
profile it loads automatically from then on.

```
Learned from 10 claps (2 discarded as not-a-clap) and 6 gaps:
  brightness floor  hf_min    0.412
  spike threshold   ratio     11.4x over your background
  quietest allowed  abs_min   0.00631
  rhythm sloppiness tolerance 0.187
```

Training listens *permissively* on purpose — a missed example costs more than a
spurious one. Which does mean a chair scrape can sneak into the batch, and since the
thresholds are anchored on your **weakest** clap rather than your average one, a single
piece of junk would drag the bar down and leave you with a hair trigger. So anything
far below the median of the batch gets thrown out first, and it tells you how many.

The header always says which it's using:

```
  profile:  trained on 10 claps
  profile:  untrained (run: clapoff --train)
```

`--no-profile` goes back to the factory guesses. `--tolerance` still wins over the
learned one if you pass it explicitly.

## Not falling for your own speakers

The detector cannot tell a hi-hat from a clap, because acoustically there is barely a
difference. So rather than get cleverer about that, clapoff cheats: it also listens to
what your computer is *playing*. If the speakers popped 200 ms ago, the microphone is
about to hear that pop, and it doesn't count.

```bash
pip install "clapoff[loopback]"     # pulls in soundcard
clapoff                             # on by default when it's available
clapoff --loopback off              # if you'd rather it didn't
```

The header tells you whether it's actually running, because a safety feature that
silently isn't there is worse than no safety feature:

```
  speakers: watching "Speakers (Realtek Audio)"
  speakers: off - soundcard not installed (pip install 'clapoff[loopback]')
```

This is **not** acoustic echo cancellation. There's no adaptive filter and nothing is
subtracted. We aren't removing your speakers from the signal, just recognising their
handwriting. It's about sixty lines.

| Platform | How | Works? |
| --- | --- | --- |
| Windows | WASAPI loopback | ✅ |
| Linux | PulseAudio monitor source | ✅ |
| macOS | needs [BlackHole](https://github.com/ExistentialAudio/BlackHole) or similar | ⚠️ BYO loopback device |

Fair warning: plenty of laptop microphone arrays already run echo cancellation in the
driver and strip speaker audio before it ever reaches us. If your machine does that,
this feature will look like it's doing nothing, because there's nothing left to do.
It earns its keep on desktops and external mics, which don't get that for free.

## Only claps from the couch

With two or more *real* microphones you can tell where a clap came from. Sound takes
about three samples per centimetre to cross from one capsule to the next, so
cross-correlating the channels (GCC-PHAT, which keeps phase and throws away magnitude —
exactly right for a broadband transient in a live room) gives you a delay fingerprint.
Train the one from where you sit, and a clap from the TV can be ignored.

```bash
clapoff --check-array       # is my mic actually an array?
clapoff --train-direction   # clap six times from your chair
```

**Check first, and expect bad news.** Most laptop "microphone arrays" beamform in the
driver and hand you one processed mono stream copied across every channel. They look
like arrays and contain no spatial information at all. Here's a real result, from the
Intel Smart Sound array this was built on:

```
  ch0  rms 0.001219  reference
  ch1  rms 0.001219  duplicate of ch0  corr vs ch0 +0.9998
  ch2  rms 0.000015  silent
  ch3  rms 0.000015  silent

Not usable: the driver is beamforming for you - every channel is the same signal,
so there's no direction left to recover.
```

Four channels, one microphone's worth of information. `--train-direction` refuses to
save a fingerprint built on that, because a direction gate fitted to noise would reject
your real claps at random and you would never work out why. Desktop arrays, ReSpeakers
and anything going through an audio interface generally do give you the real thing.

## Knowing when not to

A clap detector has no idea what you're doing. You could be presenting, in a call, or
forty minutes into a boss fight, and three claps still means three claps. So before
anything session-ending happens, clapoff asks Windows two questions:

1. **Is something full screen, or has the shell been told to shut up?**
   `SHQueryUserNotificationState` — the same call Windows itself uses to decide whether
   popping a toast would be rude. If it's rude to interrupt you, it's ruder to power off.
2. **Is another app holding the microphone?** This is the good one. If something else
   has the mic open, you are almost certainly talking to a human being, and they will
   notice you leave.

```
[14:32:08] not now - zoom.exe is using the microphone - you're probably talking to someone.
[14:32:08] (clapoff --guards off if you disagree)
```

The mic check has a trap in it, and this project fell in it. Windows records a stop
time when an app releases the microphone — but an app that *crashes* never writes one,
and the zero sits in the registry forever. On the machine this was built on,
`linguascope.exe` claimed the microphone and had not been running for who knows how
long. As a default that would have blocked shutdown **permanently**, for a reason
nobody would ever have guessed. So anything not in the live process list doesn't get a
vote.

Only session-ending actions are guarded — locking your screen goes through regardless.
`--guards off` if you disagree with all of this.

## Does it actually work

There is a test suite. It feeds synthetic audio through the detector, so it runs on
CI machines that have never heard a sound in their lives. Six of the tests go further
and hand `main()` a **fake microphone** playing synthetic claps, so the whole path —
detect, match the rhythm, count down, act — is exercised without hardware or hands.

| It must hear | It must ignore |
| --- | --- |
| ✅ three claps in a quiet room | 🚫 four seconds of music |
| ✅ quiet claps from across the room | 🚫 doors, footsteps, dropped books |
| ✅ **claps while music is playing** | 🚫 silence (a surprisingly real failure mode) |
| ✅ claps from very quiet to very loud | 🚫 shouting, TV, anything that sustains |
| ✅ the whole app, end to end, on a fake mic | 🚫 anything your own speakers just played |

```bash
pip install -e ".[dev]" && pytest
```

## How it actually works

The naive version sets a loudness threshold and calls anything above it a clap. That
version works beautifully in a silent room and goes **completely deaf** the second you
put music on — because now every block of audio is "loud," so nothing ever looks like
a sudden onset. This was not a hypothetical. It was the first version, and it failed
exactly one test, which is how you find out.

So instead:

1. **Chop** the mic into 16 ms blocks.
2. **Measure** the energy above 2 kHz, where claps live and bass does not.
3. **Compare** it to a rolling median of the last 0.75 seconds — a *relative* spike,
   not an absolute level. This is the part that survives music.
4. **Wait.** A real clap is gone in milliseconds. If the spike is still going 225 ms
   later, it was a chord, and the detection is taken back. You'll see it say
   `never mind` in the log, which is more grace than most software shows.
5. **Wait for the end.** A rhythm is over when you stop clapping. After 0.6 s of
   silence, the gaps get normalised and compared against every pattern you've
   configured. Onsets closer than 120 ms apart are one clap and its echo off your wall,
   not two claps.

## Autostart

Because a clap detector that isn't running is just a folder.

**Windows** — registers a hidden logon task:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-autostart.ps1
```

**Linux** — systemd user service:
```bash
mkdir -p ~/.config/systemd/user && cp scripts/clapoff.service ~/.config/systemd/user/
systemctl --user enable --now clapoff
```

**macOS** — launchd agent:
```bash
cp scripts/com.clapoff.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.clapoff.plist
```

Running hidden means no console, so the countdown goes to the **desktop** instead —
a notification when it starts and another if you cancel it. Fifteen seconds of
unexplained beeping isn't a warning, it's a haunting.

| Platform | How |
| --- | --- |
| Windows | WinRT toast via `powershell.exe` (not `pwsh` — PowerShell 7 can't load those types) |
| macOS | `osascript display notification` |
| Linux | `notify-send` |

If the desktop won't take them, it stops trying and says so in the header rather than
retrying forever. `--notify off` if you'd rather it kept quiet.

⚠️ Hidden also means **no keyboard abort** — clap-to-abort is the only one. Choose your
countdown accordingly.

## FAQ

**Will this shut down my PC during a drum solo?**
Not if the music is coming out of your own speakers - see above, it watches those and
vetoes anything they were responsible for. If the drum solo is happening *in the room*,
then yes, absolutely, and you have bigger scheduling problems than this program.

**Is it always listening to me?**
Yes, and it is deeply unimpressed. Nothing is recorded, stored, or transmitted. Audio
goes into a 16 ms buffer, becomes one number, and is overwritten forever. The code is
about 200 lines and you can read all of it in less time than this FAQ.

**Can I make it do something other than shut down?**
Edit `power.py`. It's four lines and one of them is a comment.

**It fires when my cat walks past.**
Lower `--sensitivity`. Or get a quieter cat. The `spike Nx` number in each log line is
your signal-to-noise budget — if real claps read `30x`, you have room to back off.

**Nothing happens when I clap.**
Run `clapoff --listen` and clap. If you see no lines at all, it's the microphone —
try `--list-devices` and pick the right one with `--device`. If you see
`never mind`, your claps are being retracted as sustained noise, which means you
live somewhere very reverberant. Try `--sensitivity 1.5`.

**`clapoff: command not found`**
pip put the console script somewhere your `PATH` doesn't know about - very common on
Windows. Everything still works, just say it the long way:

```bash
python -m clapoff.cli --listen
```

**How do I uninstall it?**
`pip uninstall clapoff`. You will have to type that. With your hands. The same hands.

## License

MIT. Clap responsibly.
