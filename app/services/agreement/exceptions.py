class AgreementExtractionBaseException(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class UnsupportedFileTypeException(AgreementExtractionBaseException):
    pass

class EmptyDocumentException(AgreementExtractionBaseException):
    pass

class OCRException(AgreementExtractionBaseException):
    pass

class GeminiExtractionException(AgreementExtractionBaseException):
    pass

class ConfigurationException(AgreementExtractionBaseException):
    pass

class InvalidStagingRecordException(AgreementExtractionBaseException):
    pass
