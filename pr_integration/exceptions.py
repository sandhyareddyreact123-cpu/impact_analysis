class PRIntegrationError(Exception):
    """Base exception for PR integration failures."""


class UnsupportedEventException(PRIntegrationError):
    pass


class InvalidWebhookException(PRIntegrationError):
    pass


class DuplicateEventException(PRIntegrationError):
    pass


class DiffAnalysisException(PRIntegrationError):
    pass


class ProviderException(PRIntegrationError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
