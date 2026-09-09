import io
import hashlib
from fastapi import UploadFile, HTTPException
from pypdf import PdfReader

class StatementValidator:
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    @staticmethod
    def validate_file(file: UploadFile):
        """Perform basic file format validation before reading stream."""
        filename = file.filename or ""
        is_pdf = filename.lower().endswith(".pdf") or file.content_type == "application/pdf"
        if not is_pdf:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file format: {file.filename}. Only PDF files are supported in Phase 1."
            )

    @staticmethod
    async def validate_content_and_get_hash(file: UploadFile) -> str:
        """
        Validates size, attempts to read using PyPDF to detect corruption, 
        and calculates MD5 hash for duplicate detection.
        """
        # Read content into memory
        await file.seek(0)
        content = await file.read()
        
        # Size validation
        if len(content) > StatementValidator.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds the 10MB limit. Uploaded: {len(content) / (1024*1024):.2f}MB."
            )
            
        # PDF structure / corruption validation
        try:
            pdf_stream = io.BytesIO(content)
            reader = PdfReader(pdf_stream)
            num_pages = len(reader.pages)
            if num_pages == 0:
                raise ValueError("PDF has 0 pages.")
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid or corrupted PDF file: {str(e)}"
            )
            
        # Generate MD5 hash for deduplication
        md5_hash = hashlib.md5(content).hexdigest()
        
        # Reset file pointer for subsequent storage operations
        await file.seek(0)
        
        return md5_hash
