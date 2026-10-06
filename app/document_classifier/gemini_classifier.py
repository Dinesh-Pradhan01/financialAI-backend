import json
import google.generativeai as genai
from pydantic import BaseModel
from typing import Optional
from app.config import settings
from app.document_classifier.schemas import DocumentClassificationResult, CATEGORY_NAMES

genai.configure(api_key=settings.GEMINI_API_KEY)

class GeminiClassificationResult(BaseModel):
    primary_category_id: int
    primary_category_name: str
    document_type: str

class GeminiZeroShotClassifier:
    @staticmethod
    def classify(text: str) -> DocumentClassificationResult:
        if not text or not text.strip():
            return DocumentClassificationResult(
                primary_category_id=9,
                primary_category_name=CATEGORY_NAMES.get(9, "Others / Unclassified"),
                document_type="Unclassified Document",
                confidence_score=0.1,
                method="empty_fallback"
            )
            
        system_prompt = """You are an expert document classifier for Indian corporate, banking, and statutory documents.
Your task is to assign exactly one primary category to the document based on these rules:

1: Identity, KYB & Authority
2: Registration, Legal Structure & Government Recognition (Entity existence and constitutional documents)
3: Tax & Statutory Compliance (Recurring tax & statutory filings)
4: Financial & Banking (Financial performance, cash, and banking)
5: Licenses, Permits & Regulatory Approvals (Regulated activity permissions)
6: Certifications, Accreditations & Independent Assurance (Independent voluntary standards / assurance)
7: Ownership, Governance & Capital (Ownership, governance, and capital)
8: Contracts, IP & Legal Obligations (Commercial contracts, IP rights, and disputes)
9: Others / Unclassified

Canonical rule: Assign exactly one primary category. (e.g., a lease agreement belongs primarily to Category 8, even if used as address proof).
If the document does not definitively fit into Categories 1-8, or is an irrelevant personal, marketing, or unidentifiable document, you MUST classify it as Category 9 ('Others / Unclassified'). Do not guess or force it into a business category.

Determine the specific 'document_type' (e.g., 'Founder Agreement', 'Board Resolution', 'Cap Table', 'Lease Agreement', 'Vendor Contract', 'Monthly MIS', 'Bank statements for operating accounts', 'Marketing Brochure', 'Unknown').

You must respond in strictly valid JSON format with keys:
"primary_category_id" (integer 1-9)
"primary_category_name" (string)
"document_type" (string)
"""

        model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL or "gemini-1.5-flash",
            system_instruction=system_prompt,
        )

        try:
            # We use generation config for structured output
            generation_config = genai.types.GenerationConfig(
                response_mime_type="application/json",
                response_schema=GeminiClassificationResult,
                temperature=0.1,
            )
            
            # Truncate text if needed to ensure we don't blow up context window unnecessarily
            max_chars = 100000 
            text_to_process = text[:max_chars]
            
            response = model.generate_content(
                f"Document text:\n{text_to_process}",
                generation_config=generation_config
            )
            
            data = json.loads(response.text)
            
            cat_id = data.get("primary_category_id", 9)
            cat_name = CATEGORY_NAMES.get(cat_id, data.get("primary_category_name", "Others / Unclassified"))
            doc_type = data.get("document_type") or "Unclassified Document"

            return DocumentClassificationResult(
                primary_category_id=cat_id,
                primary_category_name=cat_name,
                document_type=doc_type,
                confidence_score=0.85,
                method="gemini_zeroshot"
            )
        except Exception as e:
            # Fallback error handling to Category 9 (Others / Unclassified)
            return DocumentClassificationResult(
                primary_category_id=9,
                primary_category_name=CATEGORY_NAMES.get(9, "Others / Unclassified"),
                document_type="Unclassified Document",
                confidence_score=0.1,
                method="error_fallback"
            )
