"""The double-clickable front door.

Someone who downloaded an .exe has not read the flags and should not have to.
So: no arguments and no config means the setup window. No arguments with a
config means start listening, quietly, with the tray icon showing. Arguments
mean they knew what they wanted and get the command line.
"""

import sys

from . import settings
from .cli import main as cli_main


def configured():
    """Has anyone been through setup on this machine?"""
    return settings.settings_path().exists()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        return cli_main(argv)
    if not configured():
        from .gui import run_setup
        return run_setup()
    return cli_main(["--no-banner", "--tray"])


if __name__ == "__main__":
    sys.exit(main())
