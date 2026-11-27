"""Shared enums used across request/response schemas."""

from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class VerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    VERIFIED = "VERIFIED"


class ValidationDecision(str, Enum):
    PROCEED = "proceed"
    NEEDS_CONFIRMATION = "needs_confirmation"
    REJECT = "reject"


class QualityLabel(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    MINIMAL = "minimal"
