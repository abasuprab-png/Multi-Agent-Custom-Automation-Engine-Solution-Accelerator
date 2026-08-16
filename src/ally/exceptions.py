"""Runtime failures that are designed, not accidental."""


class AllyError(Exception):
    """Base error for the Ally runtime."""


class SequenceLockError(AllyError):
    """Raised when a stage is entered out of order or execution runs unsigned."""


class RefusalError(AllyError):
    """Raised when input is underspecified and Ally is licensed to refuse."""


class LockGateError(AllyError):
    """Raised when Lexie/RCC (execution) is given a diagnosis without a lock."""
