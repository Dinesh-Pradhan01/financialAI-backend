import os
from loguru import logger
import pymupdf  # fitz
import docx

from app.services.agreement.ocr_service import OCRService
from app.services.agreement.exceptions import EmptyDocumentException

class TextExtractor:
    @staticmethod
    def extract_text(file_path: str, mime_type: str) -> str:
        text = ""
        ext = os.path.splitext(file_path)[1].lower()

        logger.info(f"Extracting text from {file_path} (MIME: {mime_type})")

        if mime_type == "application/pdf" or ext == ".pdf":
            text = TextExtractor._extract_from_pdf(file_path)
            # Fallback to OCR if digital extraction yielded virtually nothing
            if len(text.strip()) < 50:
                logger.info("PDF appears to be scanned or contains very little text. Falling back to OCR.")
                text = OCRService.extract_text_from_pdf(file_path)
        
        elif mime_type in ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"] or ext in [".docx", ".doc"]:
            text = TextExtractor._extract_from_docx(file_path)
        
        elif mime_type in ["image/png", "image/jpeg", "image/jpg"] or ext in [".png", ".jpg", ".jpeg"]:
            logger.info("Image file detected. Routing to OCR.")
            text = OCRService.extract_text_from_image(file_path)
        else:
            # Attempt plain text read as last resort
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception:
                pass

        if not text or not text.strip():
            raise EmptyDocumentException("No readable text could be extracted from the document.")

        return text.strip()

    @staticmethod
    def _extract_from_pdf(file_path: str) -> str:
        try:
            text = ""
            with pymupdf.open(file_path) as doc:
                for page in doc:
                    text += page.get_text() + "\n"
            return text
        except Exception as e:
            logger.error(f"Failed to read PDF with PyMuPDF: {e}")
            return ""

    @staticmethod
    def _extract_from_docx(file_path: str) -> str:
        try:
            doc = docx.Document(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            return text
        except Exception as e:
            logger.error(f"Failed to read DOCX: {e}")
            return ""
