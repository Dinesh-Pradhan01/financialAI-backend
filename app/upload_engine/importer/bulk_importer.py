from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
import uuid
import re
from loguru import logger
from pydantic import ValidationError
from app.db.models.upload import ImportLogs
from app.repositories.upload import upload_history_repository

class BulkImporter:
    @staticmethod
    async def import_data(module_name: str, upload_id: str, valid_records: List[Dict[str, Any]], db: AsyncSession, imported_by: str = "system") -> Dict[str, Any]:
        logger.info(f"Starting bulk import for module: {module_name}, Upload ID: {upload_id}, Records: {len(valid_records)}")
        if not valid_records:
            logger.warning(f"No valid records provided for import in upload {upload_id}")
            return {"imported_count": 0, "failed_count": 0, "errors": ["No valid records to import."]}
            
        repo = None
        create_schema = None
        entity_id_field = ""
        
        if module_name == "employee":
            from app.repositories.employee import employee_repository
            from app.schemas.employee import EmployeeCreate
            repo = employee_repository
            create_schema = EmployeeCreate
            entity_id_field = "employee_id"
        elif module_name == "vendor":
            from app.repositories.vendor import vendor_repository
            from app.schemas.vendor import VendorCreate
            repo = vendor_repository
            create_schema = VendorCreate
            entity_id_field = "vendor_id"
        else:
            raise ValueError(f"Unknown module for import: {module_name}")
            
        history_record = await upload_history_repository.get(db, uuid.UUID(upload_id))
        
        objects = []
        schema_errors = []
        for record in valid_records:
            c_data = {k: v for k, v in record.items() if k not in ["rowId", "sourceRow", "isBlank"]}
            try:
                objects.append(create_schema(**c_data))
            except ValidationError as ve:
                err_msgs = [f"{err['loc'][0]}: {err['msg']}" for err in ve.errors()]
                schema_errors.extend(err_msgs)
                logger.error(f"Pydantic ValidationError on row {record.get('rowId')}: {err_msgs}")
            except Exception as e:
                schema_errors.append(f"Unexpected schema mapping error: {str(e)}")
                logger.error(f"Unexpected schema error on row {record.get('rowId')}: {str(e)}")
                
        if schema_errors:
            logger.warning(f"Schema mapping failed for {len(schema_errors)} fields. Aborting import.")
            return {"imported_count": 0, "failed_count": len(valid_records), "errors": schema_errors}

        logger.info(f"Successfully mapped {len(objects)} Pydantic schemas. Beginning database insert batches...")

        inserted_count = 0
        failed_count = 0
        errors = []
        
        try:
            # chunking logic (currently handled effectively by sqlalchemy bulk_insert or we chunk manually)
            # manual chunking for 200 row batches
            batch_size = 200
            for i in range(0, len(objects), batch_size):
                batch = objects[i:i + batch_size]
                await repo.bulk_insert(db, batch)
                
            inserted_count = len(objects)
            
            if history_record:
                history_record.status = "IMPORTED"
                db.add(history_record)
                
            for rec in objects:
                db.add(ImportLogs(
                    id=uuid.uuid4(),
                    upload_history_id=uuid.UUID(upload_id),
                    entity_type=module_name.upper(),
                    entity_id=getattr(rec, entity_id_field, "UNKNOWN"),
                    action="INSERT",
                    message="Successfully imported",
                    created_by=imported_by,
                    updated_by=imported_by
                ))
            await db.commit()
            logger.info(f"Import committed successfully for Upload ID: {upload_id} ({len(objects)} records)")
        except IntegrityError as ie:
            await db.rollback()
            logger.error(f"IntegrityError during database commit for upload {upload_id}: {str(ie)}")
            
            error_msg = "Database Constraint Error."
            # Extract common constraint details
            ie_str = str(ie.orig) if getattr(ie, 'orig', None) else str(ie)
            match = re.search(r'duplicate key value violates unique constraint "([^"]+)"', ie_str)
            if match:
                constraint_name = match.group(1)
                error_msg = f"Duplicate value violates unique constraint: '{constraint_name}'. This data may already exist."
            else:
                error_msg = f"Integrity error: {ie_str.splitlines()[0]}"
                
            errors.append(error_msg)
            
            if history_record:
                history_record.status = "FAILED"
                db.add(history_record)
                
            db.add(ImportLogs(
                id=uuid.uuid4(),
                upload_history_id=uuid.UUID(upload_id),
                entity_type=module_name.upper(),
                entity_id="ALL",
                action="ROLLBACK",
                message=f"Rolled back due to IntegrityError: {error_msg}",
                created_by="system",
                updated_by="system"
            ))
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.exception(f"Critical Exception during database commit for upload {upload_id}")
            if history_record:
                history_record.status = "FAILED"
                db.add(history_record)
                
            db.add(ImportLogs(
                id=uuid.uuid4(),
                upload_history_id=uuid.UUID(upload_id),
                entity_type=module_name.upper(),
                entity_id="ALL",
                action="ROLLBACK",
                message=f"Rolled back due to error: {str(e)[:250]}",
                created_by="system",
                updated_by="system"
            ))
            await db.commit()
            failed_count = len(objects)
            errors.append(f"Critical Database Error during import: {str(e)}")
            
        return {
            "imported_count": inserted_count,
            "failed_count": failed_count,
            "errors": errors
        }
