"""The setup window.

Everything clapoff does is available as a command-line flag, which is wonderful
if you like flags. This is for everybody else: five screens, a live picture of
what the microphone can hear, and a Start button.

Deliberately built on tkinter, which ships with Python. Not because tkinter is
nice - it is not nice - but because it means the downloadable version needs no
extra dependencies at all, and stays small enough to actually download.
"""

import queue
import threading
import tkinter as tk
from tkinter import ttk

from .detector import BLOCK, SR, ClapDetector
from . import patterns as pattern_lib
from . import settings as settings_lib

# Warm, friendly, and not the colour of a default tk window.
INK = "#2f2a26"
MUTED = "#8a7f76"
PAPER = "#faf6f0"
CARD = "#ffffff"
ACCENT = "#e0703f"
GREEN = "#4fa373"
LINE = "#e6ddd2"

TITLE_FONT = ("Segoe UI", 22, "bold")
STEP_FONT = ("Segoe UI", 11)
BODY_FONT = ("Segoe UI", 10)
SMALL_FONT = ("Segoe UI", 9)
MONO_FONT = ("Consolas", 10)

ACTION_CHOICES = ["shutdown", "sleep", "lock", "reboot", "nothing"]

RHYTHMS = [
    ("clap-clap-clap", [1, 1]),
    ("clap-clap ... clap", [1, 2]),
    ("clap ... clap-clap", [2, 1]),
    ("clap-clap-clap-clap", [1, 1, 1]),
]


class Ear:
    """A microphone in a background thread, reporting level and claps.

    tkinter must never be touched from here. Everything goes through a queue and
    the window picks it up on a timer, because a UI that blocks on audio is a UI
    that stops repainting the moment anything interesting happens.
    """

    def __init__(self):
        self.q = queue.Queue()
        self._stop = threading.Event()
        self._thread = None
        self.device = None
        self.sensitivity = 1.0
        self.error = None

    def start(self, device=None, sensitivity=1.0):
        self.stop()
        self.device = device
        self.sensitivity = sensitivity
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            import numpy as np
            import sounddevice as sd
        except Exception as exc:
            self.q.put(("error", f"No audio backend: {exc}"))
            return
        from .audio import Input
        det = ClapDetector(sensitivity=self.sensitivity)
        try:
            with Input(sd, self.device, 1) as stream:
                self.q.put(("rate", stream.describe()))
                while not self._stop.is_set():
                    data, _ = stream.read(BLOCK)
                    x = data[:, 0]
                    level = float(np.sqrt(np.mean(x * x)))
                    self.q.put(("level", level))
                    event = det.feed(x, _monotonic())
                    if event is not None and event[0] == "clap":
                        self.q.put(("clap", event[3]))
        except Exception as exc:
            self.q.put(("error", str(exc)))

    def stop(self):
        self._stop.set()
        self._thread = None

    def drain(self):
        """Everything heard since the last look."""
        items = []
        while True:
            try:
                items.append(self.q.get_nowait())
            except queue.Empty:
                return items


def _monotonic():
    import time
    return time.monotonic()


# Not microphones - these are the audio APIs' own routing entries, and offering
# them to somebody choosing "which ears" is just confusing.
ALIASES = ("sound mapper", "primary sound capture", "primary sound driver")


def input_devices():
    """(label, index) for every input a person would recognise as a microphone.

    Every microphone is listed once per audio API, so the raw list is the same
    two devices wearing eighteen hats - some truncated to 31 characters, some
    raw kernel endpoints called "Input ()". Picking a single API collapses it
    back to what's actually plugged in. WASAPI is the one worth having on
    Windows: fewest entries, full names, no routing pseudo-devices.
    """
    try:
        import sounddevice as sd
        devices = list(enumerate(sd.query_devices()))
        apis = {i: a["name"] for i, a in enumerate(sd.query_hostapis())}
    except Exception:
        return []

    def listing(api_name):
        return [(str(d["name"]).strip(), i) for i, d in devices
                if d["max_input_channels"] > 0
                and (api_name is None or apis.get(d["hostapi"]) == api_name)
                and not any(alias in str(d["name"]).lower() for alias in ALIASES)]

    preferred = "Windows WASAPI" if "Windows WASAPI" in apis.values() else None
    if preferred is None:
        try:
            default = devices[sd.default.device[0]][1]
            preferred = apis.get(default["hostapi"])
        except Exception:
            preferred = None
    return listing(preferred) or listing(None)


class Card(tk.Frame):
    """A white panel with a bit of breathing room."""

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=CARD, highlightbackground=LINE,
                         highlightthickness=1, **kw)


class Meter(tk.Canvas):
    """A live picture of what the microphone can hear."""

    def __init__(self, parent, width=460, height=26):
        super().__init__(parent, width=width, height=height, bg=CARD,
                         highlightthickness=0)
        self.w, self.h = width, height
        self.peak = 0.0
        self.create_rectangle(0, 0, width, height, fill="#f2ece4", outline="")
        self.bar = self.create_rectangle(0, 0, 0, height, fill=GREEN, outline="")

    def set(self, level):
        # Loudness is logarithmic and so is hearing; a linear bar looks dead.
        import math
        norm = min(1.0, max(0.0, (math.log10(max(level, 1e-5)) + 4.0) / 3.4))
        self.peak = max(norm, self.peak * 0.90)
        self.coords(self.bar, 0, 0, self.w * self.peak, self.h)
        self.itemconfig(self.bar, fill=ACCENT if self.peak > 0.82 else GREEN)


class Dots(tk.Canvas):
    """Three circles that fill in as you clap. The whole test, really."""

    def __init__(self, parent, count=3, size=34):
        super().__init__(parent, width=count * (size + 14), height=size + 8,
                         bg=CARD, highlightthickness=0)
        self.items = []
        for i in range(count):
            x = 6 + i * (size + 14)
            self.items.append(self.create_oval(x, 4, x + size, 4 + size,
                                               fill="#f0e9e0", outline=LINE, width=2))

    def show(self, filled):
        for i, item in enumerate(self.items):
            self.itemconfig(item, fill=GREEN if i < filled else "#f0e9e0",
                            outline=GREEN if i < filled else LINE)


class Step(tk.Frame):
    """One screen of the wizard."""

    title = ""
    subtitle = ""

    def __init__(self, app):
        super().__init__(app.body, bg=PAPER)
        self.app = app
        tk.Label(self, text=self.title, font=TITLE_FONT, bg=PAPER, fg=INK,
                 anchor="w").pack(fill="x", pady=(0, 2))
        if self.subtitle:
            tk.Label(self, text=self.subtitle, font=STEP_FONT, bg=PAPER, fg=MUTED,
                     anchor="w", justify="left", wraplength=560).pack(fill="x", pady=(0, 14))
        self.build()

    def build(self):
        pass

    def on_show(self):
        pass

    def on_leave(self):
        pass

    def can_advance(self):
        return True


class Welcome(Step):
    title = "clap. off. bye."
    subtitle = ("You clap your hands, your computer turns off. That is the entire "
                "idea and we have committed to it fully.")

    def build(self):
        card = Card(self)
        card.pack(fill="x", pady=4)
        tk.Label(card, text="\N{CLAPPING HANDS SIGN}", font=("Segoe UI Emoji", 46),
                 bg=CARD).pack(pady=(18, 6))
        tk.Label(card, text="Four quick questions. About a minute.",
                 font=BODY_FONT, bg=CARD, fg=INK).pack()
        tk.Label(card,
                 text=("Nothing you say is recorded, stored or sent anywhere.\n"
                       "Audio becomes one number and is thrown away immediately."),
                 font=SMALL_FONT, bg=CARD, fg=MUTED, justify="center").pack(pady=(8, 20))


class PickMic(Step):
    title = "Which ears?"
    subtitle = "Pick a microphone, then make some noise and check the bar moves."

    def build(self):
        card = Card(self)
        card.pack(fill="x", pady=4)
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=20, pady=18)

        self.devices = input_devices()
        labels = [label for label, _ in self.devices] or ["No microphone found"]
        self.choice = tk.StringVar(value=labels[0])
        ttk.Combobox(inner, textvariable=self.choice, values=labels, state="readonly",
                     font=BODY_FONT, width=52).pack(fill="x")
        self.choice.trace_add("write", lambda *_: self.restart())

        tk.Label(inner, text="What it can hear right now", font=SMALL_FONT,
                 bg=CARD, fg=MUTED, anchor="w").pack(fill="x", pady=(16, 4))
        self.meter = Meter(inner)
        self.meter.pack(fill="x")
        self.note = tk.Label(inner, text="", font=SMALL_FONT, bg=CARD, fg=MUTED, anchor="w")
        self.note.pack(fill="x", pady=(8, 0))

    def restart(self):
        index = self.selected_index()
        self.app.ear.start(index, self.app.state["sensitivity"])
        self.app.state["device"] = index

    def selected_index(self):
        for label, index in self.devices:
            if label == self.choice.get():
                return index
        return None

    def on_show(self):
        if not self.devices:
            self.note.config(text="No input devices at all. Is a microphone plugged in?")
            return
        self.restart()

    def on_leave(self):
        self.app.ear.stop()

    def pump(self, events):
        for kind, value in events:
            if kind == "level":
                self.meter.set(value)
            elif kind == "rate":
                self.note.config(text=f"Open and listening at {value}.", fg=GREEN)
            elif kind == "error":
                self.note.config(text=f"That microphone won't open: {value}", fg=ACCENT)

    def can_advance(self):
        return bool(self.devices)


class TestClap(Step):
    title = "Clap three times"
    subtitle = "Go on. Normally, how you'd actually do it. This teaches it nothing yet - it just proves it can hear you."

    def build(self):
        card = Card(self)
        card.pack(fill="x", pady=4)
        inner = tk.Frame(card, bg=CARD)
        inner.pack(padx=20, pady=20)
        self.dots = Dots(inner)
        self.dots.pack()
        self.status = tk.Label(inner, text="Listening...", font=BODY_FONT,
                               bg=CARD, fg=MUTED)
        self.status.pack(pady=(10, 6))
        self.meter = Meter(inner, width=420, height=16)
        self.meter.pack(pady=(4, 10))

        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x")
        tk.Label(row, text="Hearing too little?", font=SMALL_FONT, bg=CARD,
                 fg=MUTED).pack(side="left")
        self.sens = tk.DoubleVar(value=self.app.state["sensitivity"])
        ttk.Scale(row, from_=0.4, to=2.5, variable=self.sens, length=220,
                  command=lambda *_: self.retune()).pack(side="left", padx=10)
        self.sens_label = tk.Label(row, text="1.0x", font=SMALL_FONT, bg=CARD, fg=INK)
        self.sens_label.pack(side="left")

        tk.Button(inner, text="Try again", font=SMALL_FONT, bg=CARD, fg=MUTED,
                  relief="flat", cursor="hand2", command=self.reset).pack(pady=(10, 0))

        self.heard = 0

    def retune(self):
        value = round(self.sens.get(), 2)
        self.sens_label.config(text=f"{value:g}x")
        self.app.state["sensitivity"] = value
        self.app.ear.start(self.app.state["device"], value)
        self.reset()

    def reset(self):
        self.heard = 0
        self.dots.show(0)
        self.status.config(text="Listening...", fg=MUTED)

    def on_show(self):
        self.reset()
        self.app.ear.start(self.app.state["device"], self.app.state["sensitivity"])

    def on_leave(self):
        self.app.ear.stop()

    def pump(self, events):
        for kind, value in events:
            if kind == "level":
                self.meter.set(value)
            elif kind == "clap":
                self.heard = min(3, self.heard + 1)
                self.dots.show(self.heard)
                if self.heard >= 3:
                    self.status.config(text="That's the one. It can hear you.", fg=GREEN)
                    self.app.state["proved"] = True
                else:
                    self.status.config(text=f"Heard {self.heard}. Keep going.", fg=INK)


class Actions(Step):
    title = "What should it do?"
    subtitle = "Each rhythm can trigger something different. The gaps are what matter, not the speed."

    def build(self):
        card = Card(self)
        card.pack(fill="x", pady=4)
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=20, pady=18)
        self.rows = []
        for label, rhythm in RHYTHMS:
            row = tk.Frame(inner, bg=CARD)
            row.pack(fill="x", pady=5)
            tk.Label(row, text=label, font=MONO_FONT, bg=CARD, fg=INK,
                     width=24, anchor="w").pack(side="left")
            tk.Label(row, text="\N{RIGHTWARDS ARROW}", font=BODY_FONT, bg=CARD,
                     fg=MUTED).pack(side="left", padx=8)
            default = {"[1, 1]": "shutdown", "[1, 2]": "sleep",
                       "[2, 1]": "lock"}.get(str(rhythm), "nothing")
            var = tk.StringVar(value=default)
            ttk.Combobox(row, textvariable=var, values=ACTION_CHOICES,
                         state="readonly", width=14, font=BODY_FONT).pack(side="left")
            self.rows.append((label, rhythm, var))
        tk.Label(inner, text="\"nothing\" leaves that rhythm unused.",
                 font=SMALL_FONT, bg=CARD, fg=MUTED, anchor="w").pack(fill="x", pady=(12, 0))

    def collected(self):
        out = []
        for label, rhythm, var in self.rows:
            if var.get() != "nothing":
                out.append(pattern_lib.Pattern(var.get(), rhythm, var.get()))
        return out

    def can_advance(self):
        return bool(self.collected())


class Safety(Step):
    title = "Second thoughts"
    subtitle = "How long you get to change your mind, and when it should refuse outright."

    def build(self):
        card = Card(self)
        card.pack(fill="x", pady=4)
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=20, pady=18)

        tk.Label(inner, text="Countdown before it actually happens", font=BODY_FONT,
                 bg=CARD, fg=INK, anchor="w").pack(fill="x")
        tk.Label(inner, text="One clap during the countdown cancels it. So does any key.",
                 font=SMALL_FONT, bg=CARD, fg=MUTED, anchor="w").pack(fill="x", pady=(0, 6))
        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x", pady=(0, 14))
        self.countdown = tk.DoubleVar(value=self.app.state["countdown"])
        ttk.Scale(row, from_=3, to=60, variable=self.countdown, length=320,
                  command=lambda *_: self.tick()).pack(side="left")
        self.count_label = tk.Label(row, text="15 seconds", font=BODY_FONT, bg=CARD, fg=INK)
        self.count_label.pack(side="left", padx=12)

        self.guards = tk.BooleanVar(value=self.app.state["guards"] == "auto")
        self.speakers = tk.BooleanVar(value=self.app.state["loopback"] == "auto")
        self.notify = tk.BooleanVar(value=self.app.state["notify"] == "auto")
        self.tray = tk.BooleanVar(value=self.app.state["tray"])
        for var, text, hint in [
            (self.guards, "Never interrupt a call or a full-screen game",
             "If another app has the microphone, you're probably talking to a person."),
            (self.speakers, "Ignore anything my own speakers played",
             "Stops a drum track on your own machine from triggering it."),
            (self.notify, "Warn me on the desktop as well as beeping",
             "Matters if it starts hidden, where there's no window to look at."),
            (self.tray, "Show a little dot in the system tray",
             "Right-click it to pause before you applaud something."),
        ]:
            tk.Checkbutton(inner, text=text, variable=var, font=BODY_FONT, bg=CARD,
                           fg=INK, activebackground=CARD, selectcolor=CARD,
                           anchor="w").pack(fill="x")
            tk.Label(inner, text="     " + hint, font=SMALL_FONT, bg=CARD, fg=MUTED,
                     anchor="w").pack(fill="x", pady=(0, 6))
        self.tick()

    def tick(self):
        self.count_label.config(text=f"{int(self.countdown.get())} seconds")


class Finish(Step):
    title = "That's it"
    subtitle = "Saved. You can change any of it later by opening this window again."

    def build(self):
        card = Card(self)
        card.pack(fill="x", pady=4)
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=20, pady=18)
        self.summary = tk.Label(inner, text="", font=MONO_FONT, bg=CARD, fg=INK,
                                justify="left", anchor="w")
        self.summary.pack(fill="x")
        self.autostart = tk.BooleanVar(value=True)
        tk.Checkbutton(inner, text="Start clapoff whenever I log in",
                       variable=self.autostart, font=BODY_FONT, bg=CARD, fg=INK,
                       activebackground=CARD, selectcolor=CARD,
                       anchor="w").pack(fill="x", pady=(16, 0))
        self.note = tk.Label(inner, text="", font=SMALL_FONT, bg=CARD, fg=MUTED,
                             anchor="w", justify="left", wraplength=520)
        self.note.pack(fill="x", pady=(6, 0))

    def on_show(self):
        state = self.app.state
        lines = [f"{p.describe():<26} {p.action}" for p in state["patterns"]]
        lines.append("")
        lines.append(f"{'countdown':<26} {int(state['countdown'])} seconds")
        lines.append(f"{'sensitivity':<26} {state['sensitivity']:g}x")
        self.summary.config(text="\n".join(lines))
        self.app.finish_button()


def enable_dpi_awareness():
    """Tell Windows we'll handle our own pixels.

    Without this, Windows draws the window at 96 DPI and then bitmap-stretches
    it to your actual display, which is why unaware tkinter apps look slightly
    out of focus. It also makes the window's reported size disagree with its
    real size on screen, which is how this was noticed at all.
    """
    import platform
    if platform.system() != "Windows":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)     # per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()      # older Windows
        except Exception:
            pass


class Setup(tk.Tk):
    """The whole window."""

    BASE_SCALING = 96 / 72.0        # what the layout below was drawn against

    def __init__(self):
        enable_dpi_awareness()
        super().__init__()
        self.title("clapoff setup")
        self.configure(bg=PAPER)
        # Now that we own the pixels, scale the fonts ourselves from the real DPI.
        try:
            scaling = self.winfo_fpixels("1i") / 72.0
            self.tk.call("tk", "scaling", scaling)
        except tk.TclError:
            scaling = self.BASE_SCALING
        factor = scaling / self.BASE_SCALING
        self.geometry(f"{int(660 * factor)}x{int(505 * factor)}")
        self.minsize(int(620 * factor), int(470 * factor))

        saved = settings_lib.load()
        self.state_store = saved
        self.state = {
            "device": saved["device"],
            "sensitivity": saved["sensitivity"],
            "countdown": saved["countdown"],
            "guards": saved["guards"],
            "loopback": saved["loopback"],
            "notify": saved["notify"],
            "tray": saved["tray"],
            "patterns": [],
            "proved": False,
        }
        self.ear = Ear()
        self.saved_path = None
        self.launch = False

        header = tk.Frame(self, bg=PAPER)
        header.pack(fill="x", padx=28, pady=(20, 6))
        tk.Label(header, text="\N{CLAPPING HANDS SIGN} clapoff", font=("Segoe UI", 13, "bold"),
                 bg=PAPER, fg=ACCENT).pack(side="left")
        self.progress = tk.Label(header, text="", font=SMALL_FONT, bg=PAPER, fg=MUTED)
        self.progress.pack(side="right")

        self.body = tk.Frame(self, bg=PAPER)
        self.body.pack(fill="both", expand=True, padx=28, pady=6)

        footer = tk.Frame(self, bg=PAPER)
        footer.pack(fill="x", padx=28, pady=(6, 20))
        self.back = tk.Button(footer, text="Back", font=BODY_FONT, relief="flat",
                              bg=PAPER, fg=MUTED, cursor="hand2", command=self.go_back)
        self.back.pack(side="left")
        self.next = tk.Button(footer, text="Next", font=("Segoe UI", 10, "bold"),
                              relief="flat", bg=ACCENT, fg="white", cursor="hand2",
                              padx=22, pady=7, command=self.go_next)
        self.next.pack(side="right")
        self.hint = tk.Label(footer, text="", font=SMALL_FONT, bg=PAPER, fg=MUTED)
        self.hint.pack(side="right", padx=12)

        self.steps = [Welcome(self), PickMic(self), TestClap(self), Actions(self),
                      Safety(self), Finish(self)]
        self.index = 0
        self.show(0)
        self.after(60, self.pump)
        self.protocol("WM_DELETE_WINDOW", self.close)

    # -- navigation ---------------------------------------------------------

    def show(self, index):
        for step in self.steps:
            step.pack_forget()
        self.index = index
        step = self.steps[index]
        step.pack(fill="both", expand=True)
        step.on_show()
        self.progress.config(text=f"step {index + 1} of {len(self.steps)}")
        self.back.config(state="normal" if index else "disabled")
        self.next.config(text="Save and start" if index == len(self.steps) - 1 else "Next")
        self.hint.config(text="")

    def go_next(self):
        step = self.steps[self.index]
        if not step.can_advance():
            self.hint.config(text="Pick something first.")
            return
        step.on_leave()
        if self.index == 3:                      # actions chosen
            self.state["patterns"] = step.collected()
        if self.index == 4:                      # safety chosen
            self.state["countdown"] = round(step.countdown.get())
            self.state["guards"] = "auto" if step.guards.get() else "off"
            self.state["loopback"] = "auto" if step.speakers.get() else "off"
            self.state["notify"] = "auto" if step.notify.get() else "off"
            self.state["tray"] = bool(step.tray.get())
        if self.index == len(self.steps) - 1:
            return self.finish()
        self.show(self.index + 1)

    def go_back(self):
        if self.index:
            self.steps[self.index].on_leave()
            self.show(self.index - 1)

    def finish_button(self):
        self.next.config(text="Save and start")

    # -- audio pump ---------------------------------------------------------

    def pump(self):
        events = self.ear.drain()
        step = self.steps[self.index]
        if events and hasattr(step, "pump"):
            step.pump(events)
        self.after(60, self.pump)

    # -- saving -------------------------------------------------------------

    def finish(self):
        step = self.steps[-1]
        settings_lib.save({
            "device": self.state["device"],
            "sensitivity": self.state["sensitivity"],
            "countdown": self.state["countdown"],
            "guards": self.state["guards"],
            "notify": self.state["notify"],
            "loopback": self.state["loopback"],
            "tray": self.state["tray"],
        })
        write_patterns(self.state["patterns"])
        if step.autostart.get():
            ok, note = install_autostart()
            if not ok:
                step.note.config(text=f"Couldn't set up autostart: {note}")
                return
        self.launch = True
        self.close()

    def close(self):
        self.ear.stop()
        self.destroy()


def write_patterns(chosen, path=None):
    """Save the chosen rhythms in the same format the command line reads."""
    import json
    target = pattern_lib.config_path() if path is None else path
    from pathlib import Path
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = {"patterns": [{"name": p.name, "rhythm": ",".join(str(r) for r in p.rhythm),
                          "action": p.action} for p in chosen]}
    target.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return target


def install_autostart():
    """Ask the OS to start clapoff at login. Returns (worked, explanation)."""
    import platform
    import subprocess
    import sys
    if platform.system() != "Windows":
        return False, "only wired up for Windows so far"
    exe = sys.executable
    if exe.lower().endswith("clapoff.exe"):
        command = f'"{exe}" --no-banner'
    else:
        pythonw = exe.lower().replace("python.exe", "pythonw.exe")
        command = f'"{pythonw}" -m clapoff.cli --no-banner'
    try:
        subprocess.run(
            ["reg", "add", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
             "/v", "clapoff", "/t", "REG_SZ", "/d", command, "/f"],
            check=True, capture_output=True, timeout=15)
        return True, command
    except Exception as exc:
        return False, str(exc)


def run_setup():
    """Open the window. Returns a process exit code."""
    try:
        app = Setup()
    except tk.TclError as exc:
        print(f"No desktop to draw on ({exc}). Use the command line instead.")
        return 2
    app.mainloop()
    if getattr(app, "launch", False):
        from .cli import main as cli_main
        return cli_main(["--no-banner"])
    return 0
