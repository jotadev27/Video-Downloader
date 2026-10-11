from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    INVALID_LINK = "INVALID_LINK"
    NOT_FOUND = "NOT_FOUND"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    ACCESS_REQUIRED = "ACCESS_REQUIRED"
    DRM_PROTECTED = "DRM_PROTECTED"
    FORMAT_UNAVAILABLE = "FORMAT_UNAVAILABLE"
    NETWORK = "NETWORK"
    STORAGE = "STORAGE"
    CANCELLED = "CANCELLED"
    ENGINE = "ENGINE"
    SITE_BLOCKED = "SITE_BLOCKED"
    PROTECTION_UNAVAILABLE = "PROTECTION_UNAVAILABLE"


class AppError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = message
