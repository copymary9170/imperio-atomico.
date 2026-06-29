class DomainError(ValueError):
    """Base exception for legal-domain violations."""


class InvalidTransitionError(DomainError):
    """Raised when a workflow transition is not allowed."""


class SegregationOfDutiesError(DomainError):
    """Raised when creator, reviewer and approver controls are violated."""


class ConfidentialityError(DomainError):
    """Raised when confidentiality rules are violated."""
