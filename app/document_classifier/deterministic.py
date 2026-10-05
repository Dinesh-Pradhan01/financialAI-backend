import re
from typing import Optional
from app.document_classifier.schemas import DocumentClassificationResult, CATEGORY_NAMES

class DeterministicClassifier:
    @staticmethod
    def classify(text: str) -> Optional[DocumentClassificationResult]:
        if not text:
            return None
            
        text_upper = text.upper()
        
        # Category 1: PAN Card (regex [A-Z]{5}[0-9]{4}[A-Z]{1})
        if re.search(r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b', text_upper):
            return DocumentClassificationResult(
                primary_category_id=1,
                primary_category_name=CATEGORY_NAMES[1],
                document_type="PAN Card",
                confidence_score=1.0,
                method="deterministic"
            )
            
        # Category 2: Registration, Legal Structure & Government Recognition
        # CIN: ^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$
        if re.search(r'\b[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}\b', text_upper):
            return DocumentClassificationResult(
                primary_category_id=2,
                primary_category_name=CATEGORY_NAMES[2],
                document_type="Certificate of Incorporation (CIN)",
                confidence_score=1.0,
                method="deterministic"
            )
        # LLPIN: ^[A-Z]{3}-[0-9]{4}$
        if re.search(r'\b[A-Z]{3}-[0-9]{4}\b', text_upper):
            return DocumentClassificationResult(
                primary_category_id=2,
                primary_category_name=CATEGORY_NAMES[2],
                document_type="Certificate of Incorporation (LLPIN)",
                confidence_score=1.0,
                method="deterministic"
            )
        # Udyam Registration: UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}
        if re.search(r'\bUDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}\b', text_upper):
            return DocumentClassificationResult(
                primary_category_id=2,
                primary_category_name=CATEGORY_NAMES[2],
                document_type="Udyam Registration",
                confidence_score=1.0,
                method="deterministic"
            )
            
        # Category 3: Tax & Statutory Compliance
        # GST Returns: GSTR-1, GSTR-3B, GSTIN regex
        # GSTIN: 2 digits, 5 chars, 4 digits, 1 char, 1 digit/char, Z, 1 digit/char
        if "GSTR-1" in text_upper:
            return DocumentClassificationResult(
                primary_category_id=3,
                primary_category_name=CATEGORY_NAMES[3],
                document_type="GSTR-1",
                confidence_score=1.0,
                method="deterministic"
            )
        if "GSTR-3B" in text_upper:
            return DocumentClassificationResult(
                primary_category_id=3,
                primary_category_name=CATEGORY_NAMES[3],
                document_type="GSTR-3B",
                confidence_score=1.0,
                method="deterministic"
            )
        if re.search(r'\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b', text_upper):
            return DocumentClassificationResult(
                primary_category_id=3,
                primary_category_name=CATEGORY_NAMES[3],
                document_type="GST Document",
                confidence_score=1.0,
                method="deterministic"
            )
        # ROC annual filings (AOC-4, MGT-7)
        if "AOC-4" in text_upper:
            return DocumentClassificationResult(
                primary_category_id=3,
                primary_category_name=CATEGORY_NAMES[3],
                document_type="AOC-4",
                confidence_score=1.0,
                method="deterministic"
            )
        if "MGT-7" in text_upper:
            return DocumentClassificationResult(
                primary_category_id=3,
                primary_category_name=CATEGORY_NAMES[3],
                document_type="MGT-7",
                confidence_score=1.0,
                method="deterministic"
            )
        # EPFO / ESIC challans
        if "EPFO" in text_upper or "ESIC" in text_upper or "EMPLOYEES' PROVIDENT FUND" in text_upper or "EMPLOYEES' STATE INSURANCE" in text_upper:
            if "CHALLAN" in text_upper:
                return DocumentClassificationResult(
                    primary_category_id=3,
                    primary_category_name=CATEGORY_NAMES[3],
                    document_type="EPFO / ESIC Challan",
                    confidence_score=1.0,
                    method="deterministic"
                )

        # Category 6: Certifications, Accreditations & Independent Assurance
        # ISO 9001, ISO/IEC 27001, SOC 2, NABH
        for cert in ["ISO 9001", "ISO/IEC 27001", "SOC 2", "NABH"]:
            if cert in text_upper:
                return DocumentClassificationResult(
                    primary_category_id=6,
                    primary_category_name=CATEGORY_NAMES[6],
                    document_type=cert,
                    confidence_score=1.0,
                    method="deterministic"
                )

        return None
