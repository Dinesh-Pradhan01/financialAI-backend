import sys
import json
from pydantic import ValidationError
from app.upload_engine.preview.preview_builder import PreviewBuilder
from app.schemas.employee import EmployeePreviewResponse

issues = []
records = [
    {
        "rowId": "r1",
        "sourceRow": 1,
        "isBlank": False,
        "employee_id": "EMP1",
        "email": "",
        "employee_name": "John Doe",
    }
]

preview_data = PreviewBuilder.build("123", records, issues)
try:
    resp = EmployeePreviewResponse(**preview_data)
    print("Success")
except ValidationError as e:
    print("Validation Error:")
    print(e.json())
