from core.exceptions.base import BaseAppException

class AccessDeniedException(BaseAppException):
    status_code = 403
