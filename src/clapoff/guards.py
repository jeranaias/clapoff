"""Reasons not to turn the computer off right now.

A clap detector has no idea what you're doing. You could be presenting, in a
call, or forty minutes into a boss fight, and three claps still means three
claps. So before anything session-ending happens, we ask the operating system
two questions it's happy to answer:

  1. Is something running full screen, or has the shell been told to shut up?
  2. Is another application currently holding the microphone?

Question two is the good one. If something else has the mic open, you are
almost certainly talking to a human being, and they will notice you leave.
"""

import platform

# SHQueryUserNotificationState, which is how Windows already decides whether it
# is rude to pop a toast. If it's rude to interrupt you, it's ruder to power off.
QUNS_BUSY = 2
QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_PRESENTATION_MODE = 4
QUNS_APP = 7

BLOCKING_STATES = {
    QUNS_BUSY: "something is running full screen",
    QUNS_RUNNING_D3D_FULL_SCREEN: "a full-screen game is running",
    QUNS_PRESENTATION_MODE: "you're in presentation mode",
    QUNS_APP: "a full-screen app is running",
}

MIC_KEY = (r"SOFTWARE\Microsoft\Windows\CurrentVersion"
           r"\CapabilityAccessManager\ConsentStore\microphone")


def describe_state(code):
    """Turn a shell notification state into a reason, or None if it's fine."""
    return BLOCKING_STATES.get(code)


def other_microphone_users(entries, own, running=None):
    """Which of these apps is holding the mic right now, other than us?

    `entries` is (name, last_used_stop) pairs. Windows writes a stop time when an
    app lets go of the microphone, so a stop time of zero means it still has it.

    Except when it doesn't. An app that crashes never writes its stop time, and
    the zero sits in the registry forever. Measured on the machine this was built
    on: linguascope.exe claimed the microphone and had not been running for who
    knows how long - which as a default would have blocked shutdown permanently,
    for a reason nobody would ever have guessed. So if a process list is
    available, an app that isn't running doesn't get a vote.
    """
    own = (own or "").lower()
    alive = {r.lower() for r in running} if running is not None else None
    busy = []
    for name, stop in entries:
        if stop != 0:
            continue
        pretty = str(name).rstrip("\\").split("\\")[-1].split("#")[-1]
        if own and (pretty.lower() in own or own in pretty.lower()):
            continue          # that's us, holding the mic to listen for claps
        if alive is not None and pretty.lower() not in alive:
            continue          # stale entry from something that died
        busy.append(pretty)
    return busy


def running_processes():
    """Names of running processes, or None if we can't find out."""
    import subprocess
    system = platform.system()
    try:
        if system == "Windows":
            out = subprocess.run(["tasklist", "/fo", "csv", "/nh"],
                                 capture_output=True, text=True, timeout=10).stdout
            return {line.split('","')[0].lstrip('"').lower()
                    for line in out.splitlines() if line.strip()}
        out = subprocess.run(["ps", "-eo", "comm="],
                             capture_output=True, text=True, timeout=10).stdout
        return {line.strip().split("/")[-1].lower() for line in out.splitlines() if line.strip()}
    except (OSError, subprocess.SubprocessError):
        return None


def _read_windows_state():
    import ctypes
    state = ctypes.c_int(0)
    if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return None
    return state.value


def _read_windows_mic_entries():
    import winreg
    entries = []
    for root in (MIC_KEY, MIC_KEY + r"\NonPackaged"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, root) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    name = winreg.EnumKey(key, i)
                    if name == "NonPackaged":
                        continue
                    try:
                        with winreg.OpenKey(key, name) as sub:
                            stop, _ = winreg.QueryValueEx(sub, "LastUsedTimeStop")
                            entries.append((name, stop))
                    except OSError:
                        continue
        except OSError:
            continue
    return entries


def why_not_now(system=None, own_process=None):
    """A reason to hold off, or None if now is as good a time as any."""
    system = system or platform.system()
    if system != "Windows":
        # Nothing portable and trustworthy here yet. Better to say nothing than
        # to invent a check that quietly never fires.
        return None
    try:
        reason = describe_state(_read_windows_state())
        if reason:
            return reason
    except (OSError, AttributeError):
        pass
    try:
        import sys
        own = own_process or sys.executable
        busy = other_microphone_users(_read_windows_mic_entries(), own, running_processes())
        if busy:
            return f"{busy[0]} is using the microphone - you're probably talking to someone"
    except (OSError, ImportError):
        pass
    return None


def status(system=None):
    system = system or platform.system()
    if system != "Windows":
        return f"off - nothing portable to check on {system}"
    return "watching for full screen, presentations and calls"
