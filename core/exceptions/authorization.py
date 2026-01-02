from core.exceptions.base import BaseAppException

class AuthorizationException(BaseAppException):
    status_code = 403
