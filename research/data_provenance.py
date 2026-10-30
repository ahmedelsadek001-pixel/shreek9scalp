"""Backward-compatible alias for dataset provenance APIs.

The canonical implementation lives in :mod:`research.dataset_provenance`.
"""
from research.dataset_provenance import DatasetProvenance, fingerprint_bars

__all__ = ["DatasetProvenance", "fingerprint_bars"]
