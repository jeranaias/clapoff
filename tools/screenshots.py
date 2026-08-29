"""Render every setup screen and save a picture of it.

Run:  python tools/screenshots.py [outdir]

Doubles as a smoke test - a step that can't draw itself throws here rather than
in front of somebody who just downloaded the thing.
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from PIL import ImageGrab                       # noqa: E402

from clapoff.gui import Setup                   # noqa: E402

NAMES = ["01-welcome", "02-microphone", "03-clap-test",
         "04-actions", "05-safety", "06-finish"]


def grab(app, path):
    app.update_idletasks()
    app.update()
    time.sleep(0.45)                            # let the compositor catch up
    x, y = app.winfo_rootx(), app.winfo_rooty()
    box = (x, y, x + app.winfo_width(), y + app.winfo_height())
    ImageGrab.grab(bbox=box, all_screens=True).save(path)
    return path


def main():
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
    out.mkdir(parents=True, exist_ok=True)

    app = Setup()
    app.attributes("-topmost", True)
    app.update()

    # Pre-fill the screens that would otherwise photograph empty.
    app.state["patterns"] = app.steps[3].collected()
    app.steps[2].heard = 3
    app.steps[2].dots.show(3)
    app.steps[2].status.config(text="That's the one. It can hear you.")

    for index, name in enumerate(NAMES):
        app.show(index)
        if index == 2:                          # keep the filled dots visible
            app.steps[2].heard = 3
            app.steps[2].dots.show(3)
            app.steps[2].status.config(text="That's the one. It can hear you.",
                                       fg="#4fa373")
        for _ in range(6):                      # a few frames of live meter
            app.update()
            time.sleep(0.05)
            events = app.ear.drain()
            step = app.steps[index]
            if events and hasattr(step, "pump"):
                step.pump(events)
        print("saved", grab(app, out / f"{name}.png"))

    app.ear.stop()
    app.destroy()


if __name__ == "__main__":
    main()
