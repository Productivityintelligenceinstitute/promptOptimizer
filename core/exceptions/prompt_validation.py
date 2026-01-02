from core.exceptions.base import BaseAppException

class PromptValidationException(BaseAppException):
    status_code= 400