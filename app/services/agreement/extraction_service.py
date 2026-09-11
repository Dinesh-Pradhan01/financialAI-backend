import uuid
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.db.models.agreement import AgreementExtractionResult
from app.services.agreement.document_service import DocumentService
from app.services.agreement.text_extractor import TextExtractor
from app.services.agreement.gemini_service import GeminiService
from app.services.agreement.normalization_service import NormalizationService
from app.services.agreement.validation_service import ValidationService
from app.services.agreement.merge_service import MergeService
from app.services.agreement.schemas import VendorAgreementSchema, ClientAgreementSchema
from app.services.agreement.exceptions import AgreementExtractionBaseException

class ExtractionService:
    @staticmethod
    async def process_extraction(
        document_id: str,
        preview_row_id: str,
        upload_id: str,
        entity_type: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Orchestrates the agreement document extraction.
        1. Read document text (PDF/OCR)
        2. Gemini structured extraction
        3. Normalize
        4. Validate
        5. Calculate confidence
        6. Store Extraction Result
        7. Merge into Staging Row
        """
        doc_uuid = uuid.UUID(document_id)
        
        # Determine schema based on context
        if entity_type.lower() == "client":
            schema = ClientAgreementSchema
        else:
            schema = VendorAgreementSchema

        # Get document from DB to find file path
        # Assuming we just query it directly using document_id
        from sqlalchemy import select
        from app.db.models.agreement import AgreementDocument
        
        result = await db.execute(select(AgreementDocument).where(AgreementDocument.id == doc_uuid))
        doc = result.scalars().first()
        
        if not doc:
            raise AgreementExtractionBaseException("Document not found.")

        doc.status = "PROCESSING"
        await db.commit()

        try:
            # 1. Text Extraction
            raw_text = TextExtractor.extract_text(doc.file_path, doc.mime_type)

            # 2. Gemini LLM Extraction
            extracted_json = GeminiService.extract_structured_data(raw_text, schema)

            # 3. Normalization
            normalized_data = NormalizationService.normalize_extracted_data(extracted_json)

            # 4. Validation
            validation_result = ValidationService.validate_extraction(normalized_data)

            # 5. Calculate Confidence (Mocked logic for LLM)
            # We can calculate a basic heuristic confidence: 95% if valid, 60% if invalid
            base_confidence = 0.95 if validation_result.valid else 0.60
            field_confidence = {k: base_confidence for k, v in normalized_data.items() if v is not None}

            # 6. Save Extraction Result to DB
            extraction_record = AgreementExtractionResult(
                document_id=doc.id,
                preview_row_id=preview_row_id,
                contract_type=normalized_data.get("contract_type"),
                contract_start_date=normalized_data.get("contract_start_date"), # This is a string YYYY-MM-DD but mapped to Date in DB, SQLAlchemy handles cast or we can use datetime.strptime
                contract_end_date=normalized_data.get("contract_end_date"),
                contract_value=normalized_data.get("contract_value"),
                currency=normalized_data.get("currency"),
                field_confidence=field_confidence,
                raw_extraction_metadata={"llm": "gemini", "status": "success"}
            )
            
            # Convert string dates to date objects for the DB
            from datetime import datetime
            if extraction_record.contract_start_date:
                extraction_record.contract_start_date = datetime.strptime(str(extraction_record.contract_start_date), "%Y-%m-%d").date()
            if extraction_record.contract_end_date:
                extraction_record.contract_end_date = datetime.strptime(str(extraction_record.contract_end_date), "%Y-%m-%d").date()

            db.add(extraction_record)

            # Update Document Status
            doc.status = "EXTRACTED"
            await db.commit()
            
            # 7. Merge into Staging Row
            # Add valid/errors to normalized_data temporarily so merge service can set status
            merge_payload = {**normalized_data, "valid": validation_result.valid}
            updated_row = await MergeService.merge_extraction_to_preview_row(
                upload_id=upload_id,
                preview_row_id=preview_row_id,
                extracted_data=merge_payload,
                db=db
            )

            return {
                "status": "success",
                "document_id": document_id,
                "preview_row_id": preview_row_id,
                "extracted_data": normalized_data,
                "validation": validation_result.model_dump(),
                "updated_staging_row": updated_row
            }

        except Exception as e:
            logger.exception("Extraction process failed")
            doc.status = "EXTRACTION_FAILED"
            doc.error_message = str(e)
            await db.commit()
            raise AgreementExtractionBaseException(f"Extraction failed: {str(e)}")
