import logging
from pypdf import PdfReader

logger = logging.getLogger(__name__)

class StatementExtractor:
    @staticmethod
    def extract_pages(file_path: str) -> list[str]:
        """
        Reads a local PDF statement and extracts selectable text page-by-page.
        Returns a list of strings, one per page.
        Raises ValueError if the PDF contains zero selectable text.
        """
        logger.info(f"Starting page-by-page text extraction for file: {file_path}")
        try:
            reader = PdfReader(file_path)
            pages_text = []
            
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages_text.append(text)
                else:
                    logger.warning(f"No selectable text found on page {i + 1} of {file_path}")

            if not pages_text:
                logger.error(f"Extracted text from {file_path} is empty. Scanned PDF or image-only PDF detected.")
                raise ValueError(
                    "This document appears to be a scanned image or image-only PDF. "
                    "Phase 1 only supports search-selectable PDF statement formats."
                )
                
            logger.info(f"Successfully extracted {len(pages_text)} pages from {file_path}")
            return pages_text
            
        except Exception as e:
            logger.error(f"Error extracting pages from PDF {file_path}: {e}")
            raise e

    @staticmethod
    def extract_text(file_path: str) -> str:
        """
        Reads a local PDF statement and extracts all selectable text page-by-page.
        Raises ValueError if the PDF contains zero selectable text (i.e. scanned document).
        """
        pages = StatementExtractor.extract_pages(file_path)
        return "\n".join(pages).strip()

