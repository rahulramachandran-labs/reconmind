"""Retail transaction reconciliation: every business rule for this domain.

The dedup key, the key-drift pair, schema-drift tolerance, the volume window
and thresholds (``rules``), the checks the specialists run (``checks``), the
severity rubric and the write-up wording (``writeups``), wired together by
``RetailReconAdapter`` (``adapter``).
"""

from app.domain.retail_recon.adapter import RetailReconAdapter

__all__ = ["RetailReconAdapter"]
