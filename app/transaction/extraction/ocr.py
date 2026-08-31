import logging

logger = logging.getLogger(__name__)

class OCRService:
    """
    Placeholder service for OCR capabilities.
    To be expanded in Phase 2 for processing scanned JPG/PNG statements or image-only PDFs.
    """
    @staticmethod
    async def extract_text_from_scanned_file(file_path: str) -> str:
        logger.warning("OCR and image support is not active in Phase 1. Returning empty string.")
        return ""
