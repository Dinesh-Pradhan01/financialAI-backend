import os
import uuid
from typing import Dict, Any
from fastapi import BackgroundTasks
from app.document_classifier.schemas import DocumentClassificationResult
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
        # Step A: Run DeterministicClassifier on the extracted text
        result = DeterministicClassifier.classify(extracted_text)
        
        # Step B: If None, call GeminiZeroShotClassifier
        if not result:
            result = GeminiZeroShotClassifier.classify(extracted_text)
            
        # Step C: Dispatch Logic
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
