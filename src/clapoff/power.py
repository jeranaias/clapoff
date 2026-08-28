"""Actually turning the computer off. The easy part, honestly."""

import platform
import subprocess


def shutdown_command():
    """The argv this platform uses to power down, or None if we have no idea."""
    system = platform.system()
    if system == "Windows":
        # shutdown.exe acquires SE_SHUTDOWN_NAME for us. Calling ExitWindowsEx
        # directly would need the privilege enabled by hand and otherwise fails
        # with ERROR_PRIVILEGE_NOT_HELD, which is a fun afternoon.
        return ["shutdown", "/s", "/t", "0"]
    if system == "Darwin":
        return ["osascript", "-e", 'tell app "System Events" to shut down']
    if system == "Linux":
        return ["systemctl", "poweroff"]
    return None


def shutdown(dry_run=False, log=print):
    """Power off. With dry_run, just say what would have happened."""
    cmd = shutdown_command()
    if cmd is None:
        log(f"No idea how to shut down {platform.system()}. Do it yourself.")
        return False
    if dry_run:
        log("DRY RUN - would have run: " + " ".join(cmd))
        return True
    log("Shutting down. It has been a pleasure.")
    try:
        subprocess.run(cmd, check=True)
        return True
    except (OSError, subprocess.CalledProcessError) as exc:
        log(f"Shutdown failed ({exc}). Your computer has chosen to live.")
        return False
