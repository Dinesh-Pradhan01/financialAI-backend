import os
import shutil
import uuid
import tempfile
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.db.models.agreement import AgreementDocument, AgreementExtractionResult
from app.services.agreement.exceptions import UnsupportedFileTypeException, EmptyDocumentException
from app.config import settings

class DocumentService:
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg"}
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "image/png",
        "image/jpeg",
    }
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

    @staticmethod
    def _validate_file(file: UploadFile) -> None:
        if not file.filename:
            raise UnsupportedFileTypeException("Filename cannot be empty")
        
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in DocumentService.ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeException(f"Unsupported file extension: {ext}")
        
        if file.content_type not in DocumentService.ALLOWED_MIME_TYPES:
            raise UnsupportedFileTypeException(f"Unsupported MIME type: {file.content_type}")

    @staticmethod
    async def save_uploaded_agreement(
        file: UploadFile,
        preview_row_id: str,
        entity_type: str,
        upload_id: str,
        db: AsyncSession
    ) -> AgreementDocument:
        DocumentService._validate_file(file)

        # Ensure staging directory exists
        staging_dir = os.path.join(settings.UPLOAD_DIR, "agreements", entity_type, str(upload_id))
        os.makedirs(staging_dir, exist_ok=True)

        file_id = str(uuid.uuid4())
        ext = os.path.splitext(file.filename)[1].lower()
        secure_filename = f"{file_id}{ext}"
        file_path = os.path.join(staging_dir, secure_filename)

        # Calculate file size and save
        file_size = 0
        with open(file_path, "wb") as buffer:
            while True:
                chunk = await file.read(8192)
                if not chunk:
                    break
                buffer.write(chunk)
                file_size += len(chunk)
        
        if file_size == 0:
            os.remove(file_path)
            raise EmptyDocumentException("Uploaded file is empty.")
        if file_size > DocumentService.MAX_FILE_SIZE:
            os.remove(file_path)
            raise UnsupportedFileTypeException(f"File exceeds maximum allowed size of {DocumentService.MAX_FILE_SIZE/1024/1024}MB.")

        await file.seek(0)

        # Check for existing document for this row, mark old as replaced? We'll just overwrite/replace the document entry
        result = await db.execute(
            select(AgreementDocument)
            .where(AgreementDocument.preview_row_id == preview_row_id)
            .where(AgreementDocument.entity_type == entity_type)
        )
        existing_doc = result.scalars().first()
        
        if existing_doc:
            # Delete old file
            if existing_doc.file_path and os.path.exists(existing_doc.file_path):
                try:
                    os.remove(existing_doc.file_path)
                except Exception as e:
                    logger.warning(f"Could not remove old agreement file {existing_doc.file_path}: {e}")
            
            existing_doc.file_name = file.filename
            existing_doc.file_path = file_path
            existing_doc.mime_type = file.content_type
            existing_doc.file_size = file_size
            existing_doc.status = "UPLOADED"
            existing_doc.error_message = None
            doc = existing_doc
        else:
            doc = AgreementDocument(
                preview_row_id=preview_row_id,
                entity_type=entity_type,
                upload_id=upload_id,
                file_name=file.filename,
                file_path=file_path,
                mime_type=file.content_type,
                file_size=file_size,
                status="UPLOADED"
            )
            db.add(doc)

        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    async def get_active_document(preview_row_id: str, db: AsyncSession) -> AgreementDocument | None:
        result = await db.execute(
            select(AgreementDocument).where(AgreementDocument.preview_row_id == preview_row_id)
        )
        return result.scalars().first()

    @staticmethod
    async def get_latest_extraction(document_id: uuid.UUID, db: AsyncSession) -> AgreementExtractionResult | None:
        result = await db.execute(
            select(AgreementExtractionResult)
            .where(AgreementExtractionResult.document_id == document_id)
            .order_by(AgreementExtractionResult.created_at.desc())
        )
        return result.scalars().first()
