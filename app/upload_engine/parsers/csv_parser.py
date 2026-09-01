import pandas as pd
from typing import List, Dict, Any
from app.upload_engine.parsers.excel_parser import ExcelParser

class CSVParser(ExcelParser):
    def parse(self, file_path: str, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        df = pd.read_csv(file_path, dtype=str)
        return self._normalize_headers_and_parse(df, schema)
