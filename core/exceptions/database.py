from core.exceptions.base import BaseAppException

class DatabaseException(BaseAppException):
    status_code = 500
