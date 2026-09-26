"""Small logging facade used by the strategy runtime and CI."""
from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """Return a consistently configured module logger without side effects."""
    return logging.getLogger(name)
