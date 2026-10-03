"""Phase 9 content production: batch orchestration, research archive and safe merge.

This package lives OUTSIDE the fingerprinted folders (certification, solver,
sudoku, rating). It only *calls* the generator and the certifier; it never
changes how a puzzle is rated or certified. The only source of a production
certification status is a fresh ``certify_puzzle`` run with the default
``CertificationConfig()`` inside ``production-merge``.
"""
from .models import ARCHIVE_KIND, ARCHIVE_VERSION, Phase9Reason, reason_for_result
from .suitability import SUITABILITY_VERSION, SuitabilityAssessment, assess_suitability

__all__ = ["ARCHIVE_KIND", "ARCHIVE_VERSION", "Phase9Reason", "reason_for_result",
           "SUITABILITY_VERSION", "SuitabilityAssessment", "assess_suitability"]
