class DocumentExistsError(Exception):
    """Raised when attempting to add a document that already exists in the project"""
    pass

class InvalidFileTypeError(Exception):
    """Raised when attempting to upload a file type that is not supported"""
    pass
