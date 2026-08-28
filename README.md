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

  mode:    ARMED - this will really turn your computer off
  ears:    Microphone Array (Intel Smart Sound)
  trigger: 3 claps inside 2s
  abort:   15s - clap once, or press any key
  quit:    Ctrl+C

[14:32:07] clap 1/3   (rms 0.0412  hf 71%  spike 34x)
[14:32:07] clap 2/3   (rms 0.0388  hf 68%  spike 29x)
[14:32:08] clap 3/3   (rms 0.0455  hf 74%  spike 41x)
[14:32:08] THAT'S 3. Powering off in 15s - clap or hit a key if you didn't mean it.
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
clapoff --claps 4          # for people with loud lives
clapoff --sensitivity 1.5  # it's not hearing you
clapoff --sensitivity 0.6  # it's hearing things that aren't there
clapoff --list-devices     # every mic your machine admits to having
clapoff --device 3         # use that one instead
```

## Does it actually work

There is a test suite. It feeds synthetic audio through the detector, so it runs on
CI machines that have never heard a sound in their lives.

| It must hear | It must ignore |
| --- | --- |
| ✅ three claps in a quiet room | 🚫 four seconds of music |
| ✅ quiet claps from across the room | 🚫 doors, footsteps, dropped books |
| ✅ **claps while music is playing** | 🚫 silence (a surprisingly real failure mode) |
| ✅ claps from very quiet to very loud | 🚫 shouting, TV, anything that sustains |

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
5. **Count.** Three of those inside two seconds, spaced at least 120 ms apart so one
   clap and its echo off your wall don't count as two.

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

⚠️ Running hidden means no console, which means **no keyboard abort**. Clap-to-abort
still works. Choose your countdown accordingly.

## FAQ

**Will this shut down my PC during a drum solo?**
Maybe! A hi-hat is, acoustically, a clap with better time. Three of them inside two
seconds is a legitimate trigger and the detector cannot tell the difference, because
there isn't one. That's what the fifteen seconds of beeping are for. Raise `--claps`
if you listen to a lot of funk.

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
