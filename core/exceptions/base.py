class BaseAppException(Exception):
    status_code = 400

    def __init__(self, message: str):
        self.message = message
