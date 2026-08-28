"""Telling you something is about to happen, when there's no console to tell.

Running hidden at logon means no terminal, which means the countdown is fifteen
seconds of unexplained beeping. That's not a warning, that's a haunting. So the
countdown also goes to the desktop notification system, which every platform
provides and each one does completely differently.

Everything here is fire-and-forget. A notification that blocks the audio loop
would be worse than no notification at all.
"""

import platform
import subprocess

APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

# Windows has no notify-send. It has WinRT, reachable from Windows PowerShell -
# note powershell.exe and not pwsh, because PowerShell 7 usually can't load
# these types. Borrowing PowerShell's own AppID is what gets it past the shell's
# "who are you" check without registering a shortcut in the Start menu.
_WINDOWS_TOAST = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
    " ContentType=WindowsRuntime] > $null;"
    "$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
    "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
    "$t = $x.GetElementsByTagName('text');"
    "$t.Item(0).AppendChild($x.CreateTextNode('{title}')) > $null;"
    "$t.Item(1).AppendChild($x.CreateTextNode('{body}')) > $null;"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app}')"
    ".Show([Windows.UI.Notifications.ToastNotification]::new($x))"
)


def _ps_quote(text):
    """PowerShell single-quoted strings escape a quote by doubling it."""
    return str(text).replace("'", "''")


def command_for(title, body, system=None):
    """The argv that puts this on screen, or None on a platform we don't know."""
    system = system or platform.system()
    if system == "Windows":
        script = _WINDOWS_TOAST.format(title=_ps_quote(title), body=_ps_quote(body),
                                       app=_ps_quote(APP_ID))
        return ["powershell.exe", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-Command", script]
    if system == "Darwin":
        body_q = str(body).replace('"', r"\"")
        title_q = str(title).replace('"', r"\"")
        return ["osascript", "-e",
                f'display notification "{body_q}" with title "{title_q}"']
    if system == "Linux":
        return ["notify-send", "-a", "clapoff", str(title), str(body)]
    return None


class Notifier:
    """Sends desktop notifications, or quietly doesn't."""

    def __init__(self, enabled=True, spawn=None):
        self.enabled = enabled
        self.spawn = spawn or self._spawn
        self.failed = False

    @staticmethod
    def _spawn(argv):
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def send(self, title, body):
        """Fire and forget. Returns whether it went out."""
        if not self.enabled or self.failed:
            return False
        argv = command_for(title, body)
        if argv is None:
            self.failed = True
            return False
        try:
            self.spawn(argv)
            return True
        except OSError:
            # No notify-send, no PowerShell, locked-down box - stop trying.
            self.failed = True
            return False

    def status(self):
        if not self.enabled:
            return "off"
        if self.failed:
            return "off - the desktop wouldn't take them"
        return "on"
