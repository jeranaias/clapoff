"""Actually doing the thing. Still the easy part."""

import platform
import subprocess

# Per-platform incantations. Windows is the one with the comma in the middle of
# an argument, which is not a typo, it is just Windows.
COMMANDS = {
    "Windows": {
        # shutdown.exe acquires SE_SHUTDOWN_NAME for us. Calling ExitWindowsEx
        # directly needs the privilege enabled by hand and otherwise fails with
        # ERROR_PRIVILEGE_NOT_HELD, which is a fun afternoon.
        "shutdown": ["shutdown", "/s", "/t", "0"],
        "reboot": ["shutdown", "/r", "/t", "0"],
        "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
        "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
    },
    "Darwin": {
        "shutdown": ["osascript", "-e", 'tell app "System Events" to shut down'],
        "reboot": ["osascript", "-e", 'tell app "System Events" to restart'],
        "sleep": ["pmset", "sleepnow"],
        "lock": ["pmset", "displaysleepnow"],
    },
    "Linux": {
        "shutdown": ["systemctl", "poweroff"],
        "reboot": ["systemctl", "reboot"],
        "sleep": ["systemctl", "suspend"],
        "lock": ["loginctl", "lock-session"],
    },
}

FAREWELLS = {
    "shutdown": "Shutting down. It has been a pleasure.",
    "reboot": "Rebooting. See you in a minute.",
    "sleep": "Going to sleep. Don't wake me.",
    "lock": "Locking up.",
}


def command_for(action):
    """The argv for this action on this platform, or None if we have no idea."""
    return COMMANDS.get(platform.system(), {}).get(action)


def perform(action, command=None, dry_run=False, log=print):
    """Run an action. `command` is the shell string for action='command'."""
    if action == "command":
        if not command:
            log("that pattern has no command attached to it")
            return False
        if dry_run:
            log(f"DRY RUN - would have run: {command}")
            return True
        log(f"running: {command}")
        try:
            subprocess.Popen(command, shell=True)
            return True
        except OSError as exc:
            log(f"couldn't run it ({exc})")
            return False

    argv = command_for(action)
    if argv is None:
        log(f"No idea how to {action} on {platform.system()}. Do it yourself.")
        return False
    if dry_run:
        log("DRY RUN - would have run: " + " ".join(argv))
        return True
    log(FAREWELLS.get(action, f"{action}."))
    try:
        subprocess.run(argv, check=True)
        return True
    except (OSError, subprocess.CalledProcessError) as exc:
        log(f"{action} failed ({exc}). Your computer has chosen to live.")
        return False
