"""Independent final certification, separate from preliminary evolution rating."""
from .config import CertificationConfig, CERTIFICATION_VERSION
from .models import (CertificationStatus, CertificationResult, SearchStatus, FailureReason,
                     ThresholdResult, EnumerationResult)

def certify_puzzle(*args, **kwargs):
    # Logical modules can be imported with the exact solver unavailable.
    from .pipeline import certify_puzzle as certify
    return certify(*args, **kwargs)

__all__ = ["CertificationConfig", "CertificationStatus", "CertificationResult", "SearchStatus",
           "FailureReason", "certify_puzzle", "CERTIFICATION_VERSION"]
