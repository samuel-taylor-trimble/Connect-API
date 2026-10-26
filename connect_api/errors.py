"""Errors returned by Trimble ID or the Connect API."""


class TrimbleError(Exception):
    def __init__(self, message: str, *, status: int | None = None, error: str | None = None):
        super().__init__(message)
        self.status = status
        self.error = error
