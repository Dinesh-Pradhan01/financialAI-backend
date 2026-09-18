from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.client import ClientMaster
from app.services.client_compare_service import ClientComparisonService
from app.services.client_validation_service import ClientValidationService


class ClientService:
    @staticmethod
    async def get_by_business_key(db: AsyncSession, business_id: str, client_id: str, category: str) -> Optional[ClientMaster]:
        stmt = select(ClientMaster).where(
            ClientMaster.business_id == business_id,
            ClientMaster.client_id == client_id,
            ClientMaster.category == category,
            ClientMaster.is_deleted == False,
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def list_clients(db: AsyncSession, business_id: str, skip: int = 0, limit: int = 100) -> List[ClientMaster]:
        stmt = select(ClientMaster).where(
            ClientMaster.business_id == business_id,
            ClientMaster.is_deleted == False
        ).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_client(db: AsyncSession, business_id: str, client_id: str, category: Optional[str] = None) -> Optional[ClientMaster]:
        if category:
            return await ClientService.get_by_business_key(db, business_id, client_id, category)
        stmt = select(ClientMaster).where(
            ClientMaster.business_id == business_id,
            ClientMaster.client_id == client_id,
            ClientMaster.is_deleted == False,
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    def normalize_for_db(record: Dict[str, Any]) -> Dict[str, Any]:
        from datetime import datetime
        from app.services.agreement.normalization_service import NormalizationService
        
        normalized = dict(record)
        for field in {"contract_value", "revenue"}:
            if field in normalized and normalized[field] is not None:
                try:
                    normalized[field] = float(Decimal(str(normalized[field]).replace(",", "").replace("₹", "").replace("$", "").replace("INR", "")))
                except Exception:
                    normalized[field] = normalized[field]
                    
        for field in {"contract_start_date", "contract_end_date"}:
            if field in normalized and normalized[field]:
                norm = NormalizationService._normalize_date(str(normalized[field]))
                if norm:
                    try:
                        normalized[field] = datetime.strptime(norm, "%Y-%m-%d").date()
                    except ValueError:
                        normalized[field] = None
                else:
                    normalized[field] = None
            else:
                if field in normalized:
                    normalized[field] = None
                    
        return normalized

    @staticmethod
    async def import_records(db: AsyncSession, records: List[Dict[str, Any]], imported_by: str = "system", business_id: Optional[str] = None) -> Dict[str, Any]:
        results = {"inserted": 0, "updated": 0, "skipped": 0, "rejected": 0, "records": []}
        for idx, record in enumerate(records, start=1):
            validation = ClientValidationService.validate_record(record)
            if not validation["valid"]:
                results["rejected"] += 1
                results["records"].append({"row": idx, "client_id": record.get("client_id"), "category": record.get("category"), "action": "REJECT", "validation_errors": validation["errors"]})
                continue

            key = ClientComparisonService.business_key(record)
            existing = await ClientService.get_by_business_key(db, str(business_id), key[0], key[1])
            if existing is None:
                payload = ClientService.normalize_for_db(record)
                obj = ClientMaster(
                    business_id=business_id,
                    client_id=payload.get("client_id"),
                    client_name=payload.get("client_name"),
                    category=payload.get("category"),
                    legal_name=payload.get("legal_name"),
                    industry=payload.get("industry"),
                    contract_id=payload.get("contract_id"),
                    contract_type=payload.get("contract_type"),
                    contract_start_date=payload.get("contract_start_date"),
                    contract_end_date=payload.get("contract_end_date"),
                    contract_value=float(payload.get("contract_value") or 0),
                    currency=payload.get("currency"),
                    revenue=float(payload.get("revenue") or 0),
                    payment_type=payload.get("payment_type"),
                    frequency=payload.get("frequency"),
                    recurring=payload.get("recurring"),
                    bank_name=payload.get("bank_name"),
                    account_holder_name=payload.get("account_holder_name"),
                    account_number=payload.get("account_number"),
                    ifsc_code=payload.get("ifsc_code"),
                    status=payload.get("status"),
                    created_by=imported_by,
                    updated_by=imported_by,
                )
                db.add(obj)
                results["inserted"] += 1
                results["records"].append({"row": idx, "client_id": record.get("client_id"), "category": record.get("category"), "action": "INSERT"})
            else:
                comparison = ClientComparisonService.compare_record(existing.__dict__, record)
                if comparison["action"] == "SKIP":
                    results["skipped"] += 1
                    results["records"].append({"row": idx, "client_id": record.get("client_id"), "category": record.get("category"), "action": "SKIP"})
                    continue
                for field in [
                    "client_name", "legal_name", "industry", "contract_id", "contract_type", "contract_start_date",
                    "contract_end_date", "contract_value", "currency", "revenue", "payment_type", "frequency",
                    "recurring", "bank_name", "account_holder_name", "account_number", "ifsc_code", "status",
                ]:
                    if field in record:
                        setattr(existing, field, record.get(field))
                existing.updated_by = imported_by
                results["updated"] += 1
                results["records"].append({"row": idx, "client_id": record.get("client_id"), "category": record.get("category"), "action": "UPDATE", "changed_fields": comparison["changed_fields"]})

        await db.commit()
        return results

    @staticmethod
    async def delete_client(db: AsyncSession, business_id: str, client_id: str, category: Optional[str] = None) -> bool:
        client = await ClientService.get_client(db, business_id, client_id, category)
        if client:
            client.is_deleted = True
            await db.commit()
            return True
        return False
