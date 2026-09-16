import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# List of the 8 main MSME categories
CATEGORIES = {
    "BUSINESS INCOME",
    "PAYROLL & EMPLOYEES",
    "SUPPLIERS & PROCUREMENT",
    "BUSINESS OPERATIONS",
    "SALES & MARKETING",
    "FINANCE, TAX & COMPLIANCE",
    "ASSETS & INVESTMENTS",
    "TRANSFERS & OWNER TRANSACTIONS",
    "Uncategorized"
}

class StatementNormalizer:
    @staticmethod
    def normalize_transaction(tx: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cleans and normalizes a single transaction record:
        - Determines Type (DEBIT or CREDIT)
        - Normalizes amounts to floats
        - Extracts reference numbers, UTR / UPI references, and Cheque numbers if available
        - Assigns a standardized Category
        """
        # 1. Standardize amounts
        debit = float(tx.get("debit_amount") or 0.0)
        credit = float(tx.get("credit_amount") or 0.0)
        running = float(tx.get("running_balance") or 0.0)
        
        # 2. Determine type
        tx_type = "CREDIT" if credit > 0.0 else "DEBIT"
        
        # 3. Extract UTR / UPI Reference if not already provided
        narration = tx.get("narration") or ""
        utr_upi = tx.get("utr_upi_ref")
        
        if not utr_upi:
            # UPI reference (12-digit number)
            upi_match = re.search(r"(?:upi|ref|rrn)\s*[:/]?\s*(\d{12})", narration, re.IGNORECASE)
            if upi_match:
                utr_upi = f"UPI/{upi_match.group(1)}"
            else:
                # UTR references (common patterns for Indian banks: UTIBH..., SBINR..., etc.)
                utr_match = re.search(r"\b([A-Z]{4}[A-Z0-9]{11,17})\b", narration, re.IGNORECASE)
                if utr_match:
                    utr_upi = utr_match.group(1).upper()

        # 4. Extract Cheque Number if not provided
        cheque = tx.get("cheque_number")
        if not cheque:
            cheque_match = re.search(r"(?:cheque|chq)\s*(?:no|number)?\s*[:/]?\s*(\d{6})", narration, re.IGNORECASE)
            if cheque_match:
                cheque = cheque_match.group(1)

        # 5. Extract Reference Number if not provided
        ref = tx.get("reference_number") or utr_upi or cheque

        # 6. Assign Category dynamically based on Narration keywords
        category = tx.get("category", "Uncategorized")
        if category not in CATEGORIES or category in ("Uncategorized", "uncategorized", None):
            category = StatementNormalizer.categorize_narration(narration, tx_type)

        # 7. Extract classification 
        classification = tx.get("classification")
        if not classification:
            classification = "income" if tx_type == "CREDIT" else "expense"
                
        merchant_name = tx.get("merchant_name")

        return {
            "transaction_date": tx.get("transaction_date"),
            "value_date": tx.get("value_date") or tx.get("transaction_date"),
            "narration": narration,
            "debit_amount": debit,
            "credit_amount": credit,
            "running_balance": running,
            "reference_number": ref,
            "utr_upi_ref": utr_upi,
            "cheque_number": cheque,
            "category": category,
            "type": tx_type,
            "classification": classification,
            "merchant_name": merchant_name
        }

    @staticmethod
    def categorize_narration(narration: str, tx_type: str) -> str:
        """Heuristic rules to categorize transactions based on keywords in narration."""
        narr_lower = narration.lower()
        
        if tx_type == "CREDIT":
            if any(k in narr_lower for k in ("salary", "sal", "payroll", "neft salary", "wages")):
                return "PAYROLL & EMPLOYEES"
            if any(k in narr_lower for k in ("refund", "reversal", "cashback", "capital", "owner", "partner", "director")):
                return "TRANSFERS & OWNER TRANSACTIONS"
            return "BUSINESS INCOME"
            
        else:
            if any(k in narr_lower for k in ("tax", "gst", "tds", "itd", "income tax", "emi", "loan", "bajaj finance", "hdfc bank loan", "interest", "int", "bank charges", "processing fee", "annual fee", "bounce", "insurance", "lic", "policy")):
                return "FINANCE, TAX & COMPLIANCE"
            if any(k in narr_lower for k in ("salary", "sal", "payroll", "neft salary", "wages", "swiggy", "zomato", "uber", "ola", "hotel", "flight", "cleartrip", "makemytrip")):
                return "PAYROLL & EMPLOYEES"
            if any(k in narr_lower for k in ("rent", "lease", "electricity", "water", "bescom", "airtel", "jio", "bsnl", "broadband", "recharge", "gas", "aws", "google", "microsoft", "software", "subscription", "hosting", "domain", "amazon", "flipkart", "croma", "reliance", "stationery")):
                return "BUSINESS OPERATIONS"
            if any(k in narr_lower for k in ("facebook", "google ads", "instagram", "marketing", "promotion")):
                return "SALES & MARKETING"
            if any(k in narr_lower for k in ("vendor", "supplier", "contractor", "services")):
                return "SUPPLIERS & PROCUREMENT"
            if any(k in narr_lower for k in ("zerodha", "groww", "mutual fund", "sip", "demat")):
                return "ASSETS & INVESTMENTS"
                
        return "Uncategorized"
