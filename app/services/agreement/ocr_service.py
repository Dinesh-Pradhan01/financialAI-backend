import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import os
from loguru import logger
from app.services.agreement.exceptions import OCRException

class OCRService:
    @staticmethod
    def extract_text_from_image(image_path: str) -> str:
        try:
            logger.info(f"Starting OCR for image: {image_path}")
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img)
            return text.strip()
        except Exception as e:
            logger.error(f"OCR failed for image {image_path}: {e}")
            raise OCRException(f"Image OCR failed: {str(e)}")

    @staticmethod
    def extract_text_from_pdf(pdf_path: str) -> str:
        try:
            logger.info(f"Starting OCR for PDF: {pdf_path}")
            # Ensure poppler is installed and in PATH, or specify poppler_path in convert_from_path if needed
            images = convert_from_path(pdf_path, dpi=300)
            text_blocks = []
            for i, img in enumerate(images):
                logger.info(f"Running OCR on PDF page {i+1}")
                page_text = pytesseract.image_to_string(img)
                text_blocks.append(page_text)
            
            return "\n\n".join(text_blocks).strip()
        except Exception as e:
            logger.error(f"OCR failed for PDF {pdf_path}: {e}")
            raise OCRException(f"PDF OCR failed: {str(e)}")
