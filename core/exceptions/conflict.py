from core.exceptions.base import BaseAppException

class ConflictException(BaseAppException):
    status_code = 409
