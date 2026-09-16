from typing import Dict, Any, Optional
import re
from datetime import datetime
from loguru import logger

class NormalizationService:
    @staticmethod
    def normalize_extracted_data(data: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {}
        for k, v in data.items():
            if v is None:
                if k not in normalized:
                    normalized[k] = None
                continue

            if k in ["contract_start_date", "contract_end_date"]:
                normalized[k] = NormalizationService._normalize_date(str(v))
            elif k == "contract_value":
                val, currency = NormalizationService._normalize_money(str(v))
                normalized[k] = val
                if currency and not data.get("currency"):
                    normalized["currency"] = currency
            else:
                normalized[k] = v

        if "currency" in data and data["currency"]:
            normalized["currency"] = str(data["currency"]).strip().upper()

        return normalized

    @staticmethod
    def _normalize_date(date_str: str) -> Optional[str]:
        if not date_str:
            return None
        
        # Try a few common formats
        formats = [
            "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d", "%d/%m/%Y",
            "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"
        ]
        
        clean_date = date_str.strip()
        # Remove ordinals like 1st, 2nd, 3rd, 4th
        clean_date = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', clean_date)
        
        for fmt in formats:
            try:
                dt = datetime.strptime(clean_date, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
                
        # If we can't parse it, we just return the original or None to avoid 422 errors downstream
        # Let's try returning the original and letting validation catch it, or return None if it's truly unparseable.
        # It's better to return None so the database Date column doesn't crash
        logger.warning(f"Could not normalize date string: {date_str}")
        return None

    @staticmethod
    def _normalize_money(money_str: str) -> tuple[Optional[float], Optional[str]]:
        if not money_str:
            return None, None
            
        clean_str = money_str.strip()
        currency_match = re.search(r'([A-Za-z]+|\$|€|£|₹)', clean_str)
        currency = currency_match.group(1).upper() if currency_match else None
        
        # Mapping symbols to codes
        symbol_map = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}
        if currency in symbol_map:
            currency = symbol_map[currency]
            
        # Extract digits and decimal point
        num_str = re.sub(r'[^\d.]', '', clean_str)
        try:
            return float(num_str) if num_str else None, currency
        except ValueError:
            return None, currency
