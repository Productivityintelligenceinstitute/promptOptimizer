from core.exceptions.base import BaseAppException

class NotFoundException(BaseAppException):
    status_code = 404
