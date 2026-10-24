class AuthException(Exception):
    """Base exception for authentication and authorization domain errors."""


class EmailAlreadyExistsException(AuthException):
    def __init__(self, message: str = "Email already registered"):
        super().__init__(message)


class InvalidCredentialsException(AuthException):
    def __init__(self, message: str = "Invalid email or password"):
        super().__init__(message)


class AccountSuspendedException(AuthException):
    def __init__(self, message: str = "Account is suspended"):
        super().__init__(message)


class InvalidTokenException(AuthException):
    def __init__(self, message: str = "Invalid or expired token"):
        super().__init__(message)
