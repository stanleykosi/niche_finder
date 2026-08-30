from enum import StrEnum


class ErrorCode(StrEnum):
    CONFIGURATION = "configuration_error"
    SOURCE_UNAVAILABLE = "source_unavailable"
    QUOTA_EXHAUSTED = "quota_exhausted"
    VALIDATION = "validation_error"
    NOT_FOUND = "not_found"
    CANCELLED = "cancelled"


class NicheIntelError(Exception):
    def __init__(self, message: str, code: ErrorCode = ErrorCode.VALIDATION) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ClosedModeViolation(NicheIntelError):
    def __init__(self, message: str = "Live source is disabled in closed_test mode") -> None:
        super().__init__(message, ErrorCode.SOURCE_UNAVAILABLE)

