"""Entry point for the frozen build. PyInstaller needs a script, not a module."""

import sys

from clapoff.app import main

if __name__ == "__main__":
    sys.exit(main())
