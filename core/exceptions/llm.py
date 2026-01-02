from core.exceptions.base import BaseAppException

class LLMServiceException(BaseAppException):
    status_code = 502
