import os
import uuid
from typing import Dict, Any
from fastapi import BackgroundTasks
from app.document_classifier.schemas import DocumentClassificationResult, CATEGORY_NAMES
from app.document_classifier.deterministic import DeterministicClassifier
from app.document_classifier.gemini_classifier import GeminiZeroShotClassifier
from app.statement.service import StatementProcessingService
from app.config import settings

class DocumentClassificationService:
    @staticmethod
    def classify_and_dispatch(
        extracted_text: str,
        file_bytes: bytes,
        filename: str,
        background_tasks: BackgroundTasks
    ) -> Dict[str, Any]:
        result = None
        clean_text = (extracted_text or "").strip()

        # Step A: Run DeterministicClassifier on extracted text if available
        if clean_text:
            result = DeterministicClassifier.classify(clean_text)
            
        # Step B: If None, call GeminiZeroShotClassifier
        if not result and clean_text:
            try:
                result = GeminiZeroShotClassifier.classify(clean_text)
            except Exception:
                result = None

        # Step C: If still None (e.g. empty text or image-only PDF), check filename heuristics
        if not result and filename:
            fn_upper = filename.upper()
            if "PAN" in fn_upper:
                result = DocumentClassificationResult(
                    primary_category_id=1,
                    primary_category_name=CATEGORY_NAMES.get(1, "Identity, KYB & Authority"),
                    document_type="PAN Card",
                    confidence_score=0.75,
                    method="filename_heuristic"
                )
            elif "GST" in fn_upper:
                result = DocumentClassificationResult(
                    primary_category_id=3,
                    primary_category_name=CATEGORY_NAMES.get(3, "Tax & Statutory Compliance"),
                    document_type="GST Registration",
                    confidence_score=0.75,
                    method="filename_heuristic"
                )
            elif "CIN" in fn_upper or "INCORPORATION" in fn_upper or "COI" in fn_upper:
                result = DocumentClassificationResult(
                    primary_category_id=2,
                    primary_category_name=CATEGORY_NAMES.get(2, "Registration, Legal Structure & Government Recognition"),
                    document_type="Certificate of Incorporation",
                    confidence_score=0.75,
                    method="filename_heuristic"
                )
            elif "STATEMENT" in fn_upper or "BANK" in fn_upper:
                result = DocumentClassificationResult(
                    primary_category_id=4,
                    primary_category_name=CATEGORY_NAMES.get(4, "Financial & Banking"),
                    document_type="Bank statements for operating accounts",
                    confidence_score=0.75,
                    method="filename_heuristic"
                )

        # Step D: Guaranteed safe fallback to Category 9 (Others / Unclassified)
        if not result:
            result = DocumentClassificationResult(
                primary_category_id=9,
                primary_category_name=CATEGORY_NAMES.get(9, "Others / Unclassified"),
                document_type="Unclassified Document",
                confidence_score=0.1,
                method="safe_fallback"
            )

        # Step E: Dispatch Logic
        response_data = result.model_dump()
        
        # Dispatch to StatementProcessingService if Category 4 & Bank Statement
        if result.primary_category_id == 4 and result.document_type.lower() == "bank statements for operating accounts":
            document_id = str(uuid.uuid4())
            
            # Save file locally to pass path to the service
            upload_dir = settings.UPLOAD_DIR
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, f"{document_id}_{filename}")
            
            with open(file_path, "wb") as f:
                f.write(file_bytes)
                
            # Enforce existing pipeline
            background_tasks.add_task(
                StatementProcessingService.process_statement_task,
                document_id=document_id,
                file_path=file_path
            )
            
            response_data["dispatch_note"] = "Statement transaction extraction has been scheduled."
            
        return response_data
