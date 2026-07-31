import asyncio
from sqlalchemy import select
from app.database.connection import db_manager, init_db
from app.auth.model import User
from app.business.models import (
    GeneralInfo,
    LeadershipInfo,
    FinancialInfo,
    BusinessVerificationDocument
)

async def check_db():
    await init_db()
    async with db_manager.session_factory() as session:
        print("=== 1. USERS TABLE ===")
        res = await session.execute(select(User))
        users = res.scalars().all()
        for u in users:
            print(f"ID: {u.id} | Email: {u.email} | PersonID: {u.person_id} | BusinessID: {u.business_id}")

        print("\n=== 2. BUSINESS GENERAL INFO TABLE ===")
        res = await session.execute(select(GeneralInfo))
        biz_list = res.scalars().all()
        for b in biz_list:
            print(f"ID: {b.id} | Name: {b.company_name} | Category: {b.business_category} | PAN: {b.business_pan} | Completion: {b.completion_percentage}% | Completed: {b.onboarding_completed}")

        print("\n=== 3. BUSINESS INFO TABLE ===")
        res = await session.execute(select(LeadershipInfo))
        info_list = res.scalars().all()
        for bi in info_list:
            print(f"BusinessID: {bi.business_id} | Contact: {bi.primary_contact_person} | CEO: {bi.founder_ceo_name} | Model: {bi.business_model}")

        print("\n=== 4. BUSINESS FINANCIAL INFO TABLE ===")
        res = await session.execute(select(FinancialInfo))
        fin_list = res.scalars().all()
        for fi in fin_list:
            print(f"BusinessID: {fi.business_id} | Bank: {fi.primary_bank} | Software: {fi.accounting_software} | Methods: {fi.digital_payment_methods}")

        print("\n=== 5. BUSINESS DOCUMENTS TABLE ===")
        res = await session.execute(select(BusinessVerificationDocument))
        docs = res.scalars().all()
        for d in docs:
            print(f"BusinessID: {d.business_id} | Type: {d.document_type} | File: {d.original_name} ({d.file_size_bytes} bytes)")

    await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(check_db())
