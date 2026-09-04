import pandas as pd
from typing import List, Dict, Any
import re

class ExcelParser:
    def parse(self, file_path: str, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        df = pd.read_excel(file_path, dtype=str)
        return self._normalize_headers_and_parse(df, schema)

    def _normalize_headers_and_parse(self, df: pd.DataFrame, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Flatten header variations to map to actual schema names
        header_map = {}
        for field in schema["fields"]:
            for variation in field.get("header_variations", []):
                header_map[variation.lower()] = field["name"]

        actual_headers = [str(col).lower().strip() for col in df.columns]
        
        rename_map = {}
        for col in df.columns:
            cleaned = re.sub(r'\s+', ' ', str(col).lower().strip())
            # For special chars like tax (%)
            if "tax" in cleaned and "%" in cleaned:
                cleaned = "tax (%)"
            if "payment flow" in cleaned:
                cleaned = "payment flow (debit/credit)"
            
            if cleaned in header_map:
                rename_map[col] = header_map[cleaned]
                
        df = df.rename(columns=rename_map)
        df = df.where(pd.notnull(df), None)
        
        records = []
        for _, row in df.iterrows():
            row_dict = {k: (str(v).strip() if v is not None and str(v).strip() != "" else None) 
                        for k, v in row.to_dict().items()}
            records.append(row_dict)
            
        return records
