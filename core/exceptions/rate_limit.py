from core.exceptions.base import BaseAppException

class RateLimitExceededException(BaseAppException):
    status_code = 429