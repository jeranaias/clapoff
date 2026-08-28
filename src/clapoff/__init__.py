"""clapoff - clap your hands, the computer turns off."""

from .detector import BLOCK, HF_CUT, SR, ClapDetector

__version__ = "0.1.0"
__all__ = ["ClapDetector", "SR", "BLOCK", "HF_CUT", "__version__"]
