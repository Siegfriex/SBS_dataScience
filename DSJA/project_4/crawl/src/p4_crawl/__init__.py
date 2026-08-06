"""P4 Linkareer collector package.

The package contains restartable collector primitives.  Notebooks in
``crawl/notebooks`` are deliberately thin orchestration clients.
"""

from .config import RunConfig

__all__ = ["RunConfig"]
__version__ = "0.1.0"
