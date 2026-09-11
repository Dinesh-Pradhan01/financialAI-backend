import uuid
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
import copy

from app.db.models.upload import UploadHistory
from app.services.agreement.exceptions import InvalidStagingRecordException

class MergeService:
    @staticmethod
    async def merge_extraction_to_preview_row(
        upload_id: str,
        preview_row_id: str,
        extracted_data: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Merge extracted agreement data into the specific row in UploadHistory.preview_data
        and recalculate validation status if needed.
        """
        try:
            upload_uuid = uuid.UUID(upload_id)
        except ValueError:
            raise InvalidStagingRecordException("Invalid upload_id format.")

        result = await db.execute(select(UploadHistory).where(UploadHistory.id == upload_uuid))
        history_record = result.scalars().first()

        if not history_record:
            raise InvalidStagingRecordException(f"UploadHistory record with ID {upload_id} not found.")

        preview_data = history_record.preview_data
        if not isinstance(preview_data, list):
            raise InvalidStagingRecordException("Staging data is corrupted or not a list.")

        updated = False
        target_row = None
        new_preview_data = copy.deepcopy(preview_data)

        for row in new_preview_data:
            # Check rowId or row_id matching the preview_row_id
            if str(row.get("rowId", "")) == preview_row_id or str(row.get("row_id", "")) == preview_row_id:
                # Merge the extracted fields into the row
                for key, val in extracted_data.items():
                    if val is not None:
                        row[key] = val
                
                # Update extraction status flag on the row for frontend
                row["extraction_status"] = "APPROVED" if extracted_data.get("valid", True) else "REVIEW_REQUIRED"
                if "valid" in extracted_data:
                    del extracted_data["valid"]
                    
                target_row = row
                updated = True
                break
        
        if not updated:
            raise InvalidStagingRecordException(f"Row {preview_row_id} not found in upload {upload_id}.")

        # Re-save the JSON back to the DB
        # Assign to property to trigger SQLAlchemy JSON mutation detection if necessary,
        # but using dict assignment often requires flag_modified
        from sqlalchemy.orm.attributes import flag_modified
        history_record.preview_data = new_preview_data
        flag_modified(history_record, "preview_data")
        
        await db.commit()
        logger.info(f"Successfully merged extraction data into staging row {preview_row_id}")

        return target_row
