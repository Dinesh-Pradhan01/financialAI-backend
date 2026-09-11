import os
import uuid
import time
from typing import Dict, Any, List
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.upload_engine.parsers.parser_factory import load_schema, ParserFactory
from app.upload_engine.validators.schema_validator import SchemaValidator
from app.upload_engine.validators.row_validator import RowValidator
from app.upload_engine.validators.duplicate_validator import DuplicateValidator
from app.upload_engine.validators.business_validator import BusinessValidator
from app.upload_engine.preview.preview_builder import PreviewBuilder
from app.schemas.upload import UploadHistoryCreate
from app.repositories.upload import upload_history_repository

class UploadEngine:
    def __init__(self, module_name: str):
        self.module_name = module_name
        self.schema = load_schema(module_name)
        
    def _get_normalizer(self):
        if self.module_name == "employee":
            from app.upload_engine.normalizers.employee_normalizer import EmployeeNormalizer
            return EmployeeNormalizer()
        elif self.module_name == "vendor":
            from app.upload_engine.normalizers.vendor_normalizer import VendorNormalizer
            return VendorNormalizer()
        else:
            from app.upload_engine.normalizers.base_normalizer import BaseNormalizer
            return BaseNormalizer()
            
    async def process_file(self, file: UploadFile, db: AsyncSession, uploaded_by: str = "system") -> Dict[str, Any]:
        start_time = time.time()
        
        file_ext = os.path.splitext(file.filename)[1].lower()
        parser = ParserFactory.get_parser(file_ext)
        
        upload_dir = f"uploads/{self.module_name}s"
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, f"{uuid.uuid4()}{file_ext}")
        
        with open(file_path, "wb") as buffer:
            content = await file.read()
            file_size = len(content)
            buffer.write(content)
            
        try:
            raw_records = parser.parse(file_path, self.schema)
        except Exception as e:
            raise ValueError(f"File Parsing Error: {str(e)}")
            
        return await self._process_records(raw_records, file.filename, file_size, db, uploaded_by, start_time, "UPLOAD")

    async def process_manual(self, records: List[Dict[str, Any]], db: AsyncSession, uploaded_by: str = "system") -> Dict[str, Any]:
        start_time = time.time()
        return await self._process_records(records, "manual_entry.json", 0, db, uploaded_by, start_time, "MANUAL")
        
    async def _process_records(self, raw_records: List[Dict[str, Any]], filename: str, file_size: int, db: AsyncSession, uploaded_by: str, start_time: float, upload_type: str) -> Dict[str, Any]:
        normalizer = self._get_normalizer()
        normalized_records = normalizer.normalize(raw_records)
        
        all_issues = []
        for rec in normalized_records:
            if not rec.get("isBlank"):
                row_issues = RowValidator.validate_row(rec, self.schema, rec["rowId"], rec["sourceRow"])
                all_issues.extend(row_issues)
                bus_issues = BusinessValidator.validate(self.module_name, rec, self.schema, rec["rowId"], rec["sourceRow"])
                all_issues.extend(bus_issues)
                
        dup_issues = DuplicateValidator.validate_duplicates(normalized_records, self.schema)
        all_issues.extend(dup_issues)
        
        existing_emp_ids = set()
        if self.module_name == "employee" and db is not None:
            try:
                from sqlalchemy import select
                from app.db.models.employee import EmployeeMaster
                emp_ids = [r.get("emp_id") or r.get("employee_id") for r in normalized_records if r.get("emp_id") or r.get("employee_id")]
                if emp_ids:
                    stmt = select(EmployeeMaster.employee_id).where(
                        EmployeeMaster.employee_id.in_(emp_ids),
                        EmployeeMaster.is_deleted == False
                    )
                    res = await db.execute(stmt)
                    existing_emp_ids = set(res.scalars().all())
            except Exception as ex:
                print("Error checking existing employees in preview:", ex)
                pass

        row_errors_map = {}
        for issue in all_issues:
            if issue.get("severity") == "error":
                r_id = issue.get("rowId")
                if r_id:
                    row_errors_map.setdefault(r_id, []).append(issue.get("message", ""))

        for rec in normalized_records:
            e_id = rec.get("emp_id") or rec.get("employee_id")
            if e_id:
                rec["emp_id"] = e_id
                rec["employee_id"] = e_id
            errs = row_errors_map.get(rec.get("rowId"), [])
            rec["validation_errors"] = errs
            rec["validation_status"] = "invalid" if errs else "valid"
            if e_id in existing_emp_ids:
                rec["preview_status"] = "existing_employee"
            else:
                rec["preview_status"] = "valid"

        preview_obj = PreviewBuilder.build("", normalized_records, all_issues, module_name=self.module_name)
        summary_info = preview_obj["summary"]
        
        processing_time = int((time.time() - start_time) * 1000)
        
        upload_uuid = uuid.uuid4()
        preview_obj["upload_id"] = str(upload_uuid)
        preview_obj["preview_id"] = str(upload_uuid)
        preview_obj["total_records"] = len(normalized_records)
        preview_obj["valid_records"] = summary_info["validRecords"]
        preview_obj["invalid_records"] = summary_info["errors"]
        preview_obj["schema_def"] = self.schema

        if db is not None:
            from app.db.models.upload import UploadHistory
            history_record = UploadHistory(
                id=upload_uuid,
                upload_type=f"{self.module_name.upper()}_{upload_type}",
                file_name=filename,
                file_size=file_size,
                uploaded_by=uploaded_by,
                total_records=len(normalized_records),
                success_records=summary_info["validRecords"],
                failed_records=summary_info["errors"],
                processing_time=processing_time,
                status="PREVIEW",
                preview_data=preview_obj
            )
            db.add(history_record)
            await db.commit()

        return preview_obj
