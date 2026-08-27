import logging
import os
import uuid
import hashlib
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_session_user
from app.auth.model import User
from app.database.connection import get_db
from app.business.models import (
    GeneralInfo,
    BusinessVerificationDocument,
    DocumentAuditLog,
    Package,
    PackageDocument
)
from app.company.schemas import (
    CompanyDocumentResponse,
    DocumentAuditLogResponse,
    PackageRequest,
    PackageResponse,
    PackageDocumentUpdate
)
from app.ai.llm import gemini_service
import pypdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["company-documents"])
package_router = APIRouter(prefix="/packages", tags=["company-packages"])

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads", "business_docs")
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def get_user_business(user: User, db: AsyncSession) -> GeneralInfo:
    if user.business_id:
        res = await db.execute(select(GeneralInfo).where(GeneralInfo.id == user.business_id))
        business = res.scalar_one_or_none()
        if business:
            return business
    raise HTTPException(status_code=404, detail="Business profile not found.")

def validate_file(file: UploadFile, max_size_mb: int = 10):
    ALLOWED_MIMES = ["application/pdf"]
    if file.content_type not in ALLOWED_MIMES:
        raise HTTPException(status_code=400, detail=f"Invalid file type '{file.content_type}'. Only PDF files are accepted for document verification.")

async def process_document_ai(file: UploadFile, file_bytes: bytes, document_type: str, business: GeneralInfo):
    document_text = ""
    if file.content_type == "application/pdf":
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    document_text += text + "\n"
        except Exception as e:
            logger.warning(f"Failed to extract text from PDF: {e}")

    quality_score = None
    is_verified = False
    verification_notes = None

    if document_text.strip():
        expected_id = business.business_pan if document_type == "business_pan" else (business.cin if document_type == "registration_proof" else "")
        verification_result = await gemini_service.verify_document_quality(document_text, document_type, expected_id or "")
        
        if verification_result:
            is_readable = verification_result.get("is_readable", False)
            quality_score = verification_result.get("quality_score", 0.0)
            extracted_id = verification_result.get("extracted_id")
            verification_notes = verification_result.get("notes", "")
            
            if not is_readable or quality_score < 50.0:
                raise HTTPException(status_code=400, detail=f"Document quality is too low (Score: {quality_score}). Notes: {verification_notes}")
                
            if expected_id and extracted_id and expected_id.upper() not in extracted_id.upper():
                raise HTTPException(status_code=400, detail=f"Document verification failed. Expected ID {expected_id} but found {extracted_id}.")
                
            is_verified = True
        else:
            verification_notes = "AI verification unavailable. Manual verification required."
    else:
        verification_notes = "No text extracted. Manual verification required."
        
    return quality_score, is_verified, verification_notes

async def create_audit_log(db: AsyncSession, doc_id: uuid.UUID, user_id: int, action: str):
    log = DocumentAuditLog(
        document_id=doc_id,
        user_id=user_id,
        action=action
    )
    db.add(log)

# ================= DOCUMENTS ENDPOINTS =================

@router.get("", response_model=List[CompanyDocumentResponse])
async def get_company_documents(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    docs_res = await db.execute(select(BusinessVerificationDocument).where(BusinessVerificationDocument.business_id == business.id))
    docs = docs_res.scalars().all()
    
    return [CompanyDocumentResponse.model_validate(d, from_attributes=True) for d in docs]

@router.post("", response_model=CompanyDocumentResponse)
async def upload_company_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    document_category: str = Form(...),
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    # R7: Validation
    validate_file(file)
    
    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024: # 10MB
        raise HTTPException(status_code=400, detail="File too large. Max 10MB.")
        
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    
    # Global Duplication Check
    duplicate_res = await db.execute(
        select(BusinessVerificationDocument).where(BusinessVerificationDocument.file_hash == file_hash)
    )
    if duplicate_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Duplicate document uploaded.")
        
    quality_score, is_verified, verification_notes = await process_document_ai(file, file_bytes, document_type, business)
    
    biz_dir = os.path.join(UPLOAD_DIR, str(business.id))
    os.makedirs(biz_dir, exist_ok=True)
    
    file_ext = os.path.splitext(file.filename)[1]
    safe_filename = f"{document_type}_{uuid.uuid4().hex[:8]}{file_ext}"
    file_path = os.path.join(biz_dir, safe_filename)
    
    with open(file_path, "wb") as f:
        f.write(file_bytes)
        
    new_doc = BusinessVerificationDocument(
        business_id=business.id,
        document_type=document_type,
        document_category=document_category,
        filename=safe_filename,
        original_name=file.filename,
        file_path=file_path,
        file_size_bytes=len(file_bytes),
        mime_type=file.content_type or "application/octet-stream",
        upload_status="uploaded",
        file_hash=file_hash,
        quality_score=quality_score,
        is_verified=is_verified,
        verification_notes=verification_notes,
        uploaded_by=current_user.id # R2
    )
    db.add(new_doc)
    await db.flush()
    
    # R5: Audit log
    await create_audit_log(db, new_doc.id, current_user.id, "upload")
    
    await db.commit()
    await db.refresh(new_doc)
    
    return CompanyDocumentResponse.model_validate(new_doc, from_attributes=True)


@router.put("/{doc_id}", response_model=CompanyDocumentResponse)
async def replace_company_document(
    doc_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    doc_res = await db.execute(
        select(BusinessVerificationDocument).where(
            BusinessVerificationDocument.id == doc_id,
            BusinessVerificationDocument.business_id == business.id
        )
    )
    doc = doc_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    validate_file(file)
    
    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 10MB.")
        
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    
    # Global Duplication Check
    duplicate_res = await db.execute(
        select(BusinessVerificationDocument).where(BusinessVerificationDocument.file_hash == file_hash, BusinessVerificationDocument.id != doc_id)
    )
    if duplicate_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Duplicate document uploaded.")
        
    quality_score, is_verified, verification_notes = await process_document_ai(file, file_bytes, doc.document_type, business)
    
    # Remove old file
    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception as e:
            logger.warning(f"Failed to delete old file {doc.file_path}: {e}")
            
    # Save new file
    biz_dir = os.path.join(UPLOAD_DIR, str(business.id))
    os.makedirs(biz_dir, exist_ok=True)
    file_ext = os.path.splitext(file.filename)[1]
    safe_filename = f"{doc.document_type}_{uuid.uuid4().hex[:8]}{file_ext}"
    file_path = os.path.join(biz_dir, safe_filename)
    
    with open(file_path, "wb") as f:
        f.write(file_bytes)
        
    # Update document record
    doc.filename = safe_filename
    doc.original_name = file.filename
    doc.file_path = file_path
    doc.file_size_bytes = len(file_bytes)
    doc.mime_type = file.content_type or "application/octet-stream"
    doc.file_hash = file_hash
    doc.quality_score = quality_score
    doc.is_verified = is_verified
    doc.verification_notes = verification_notes
    doc.uploaded_by = current_user.id
    
    # R5: Audit log
    await create_audit_log(db, doc.id, current_user.id, "replace")
    
    await db.commit()
    await db.refresh(doc)
    
    return CompanyDocumentResponse.model_validate(doc, from_attributes=True)


@router.delete("/{doc_id}")
async def delete_company_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    doc_res = await db.execute(
        select(BusinessVerificationDocument).where(
            BusinessVerificationDocument.id == doc_id,
            BusinessVerificationDocument.business_id == business.id
        )
    )
    doc = doc_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    # R5: Audit Log
    await create_audit_log(db, doc.id, current_user.id, "delete")
        
    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception as e:
            logger.warning(f"Could not remove file {doc.file_path}: {e}")
            
    await db.delete(doc)
    await db.commit()
    
    return {"message": "Document deleted successfully"}

@router.get("/{doc_id}/download")
async def download_company_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    doc_res = await db.execute(
        select(BusinessVerificationDocument).where(
            BusinessVerificationDocument.id == doc_id,
            BusinessVerificationDocument.business_id == business.id
        )
    )
    doc = doc_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="File physically missing from disk.")
        
    return FileResponse(
        doc.file_path, 
        filename=doc.original_name, 
        media_type=doc.mime_type
    )

# ================= PACKAGES ENDPOINTS =================

@package_router.get("", response_model=List[PackageResponse])
async def list_packages(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    res = await db.execute(
        select(Package).where(Package.business_id == business.id).options(selectinload(Package.documents).selectinload(PackageDocument.document))
    )
    packages = res.scalars().all()
    
    resp_list = []
    for p in packages:
        docs = [pd.document for pd in p.documents]
        p_dict = {
            "id": p.id,
            "name": p.name,
            "created_by": p.created_by,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
            "documents": [CompanyDocumentResponse.model_validate(d, from_attributes=True) for d in docs]
        }
        resp_list.append(PackageResponse(**p_dict))
        
    return resp_list

@package_router.post("", response_model=PackageResponse)
async def create_package(
    payload: PackageRequest,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    pkg = Package(
        business_id=business.id,
        name=payload.name,
        created_by=current_user.id
    )
    db.add(pkg)
    await db.flush()
    
    docs = []
    if payload.document_ids:
        # Validate docs belong to this business
        res = await db.execute(select(BusinessVerificationDocument).where(
            BusinessVerificationDocument.id.in_(payload.document_ids),
            BusinessVerificationDocument.business_id == business.id
        ))
        docs = res.scalars().all()
        for doc in docs:
            pd = PackageDocument(package_id=pkg.id, document_id=doc.id)
            db.add(pd)
            
    await db.commit()
    
    return PackageResponse(
        id=pkg.id,
        name=pkg.name,
        created_by=pkg.created_by,
        created_at=pkg.created_at,
        updated_at=pkg.updated_at,
        documents=[CompanyDocumentResponse.model_validate(d, from_attributes=True) for d in docs]
    )

@package_router.patch("/{pkg_id}", response_model=PackageResponse)
async def rename_package(
    pkg_id: uuid.UUID,
    payload: PackageRequest,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    res = await db.execute(select(Package).where(Package.id == pkg_id, Package.business_id == business.id).options(selectinload(Package.documents).selectinload(PackageDocument.document)))
    pkg = res.scalar_one_or_none()
    
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
        
    pkg.name = payload.name
    await db.commit()
    await db.refresh(pkg)
    
    docs = [pd.document for pd in pkg.documents]
    return PackageResponse(
        id=pkg.id,
        name=pkg.name,
        created_by=pkg.created_by,
        created_at=pkg.created_at,
        updated_at=pkg.updated_at,
        documents=[CompanyDocumentResponse.model_validate(d, from_attributes=True) for d in docs]
    )

@package_router.delete("/{pkg_id}")
async def delete_package(
    pkg_id: uuid.UUID,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    res = await db.execute(select(Package).where(Package.id == pkg_id, Package.business_id == business.id))
    pkg = res.scalar_one_or_none()
    
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
        
    await db.delete(pkg)
    await db.commit()
    
    return {"message": "Package disbanded successfully"}

@package_router.post("/{pkg_id}/documents", response_model=PackageResponse)
async def add_package_documents(
    pkg_id: uuid.UUID,
    payload: PackageDocumentUpdate,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    res = await db.execute(select(Package).where(Package.id == pkg_id, Package.business_id == business.id).options(selectinload(Package.documents).selectinload(PackageDocument.document)))
    pkg = res.scalar_one_or_none()
    
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
        
    # Validate docs exist and belong to business
    docs_res = await db.execute(select(BusinessVerificationDocument).where(
        BusinessVerificationDocument.id.in_(payload.document_ids),
        BusinessVerificationDocument.business_id == business.id
    ))
    new_docs = docs_res.scalars().all()
    
    existing_doc_ids = {pd.document_id for pd in pkg.documents}
    
    for doc in new_docs:
        if doc.id not in existing_doc_ids:
            pd = PackageDocument(package_id=pkg.id, document_id=doc.id)
            db.add(pd)
            
    await db.commit()
    
    # Reload package
    res = await db.execute(select(Package).where(Package.id == pkg_id).options(selectinload(Package.documents).selectinload(PackageDocument.document)))
    pkg = res.scalar_one_or_none()
    docs = [pd.document for pd in pkg.documents]
    
    return PackageResponse(
        id=pkg.id,
        name=pkg.name,
        created_by=pkg.created_by,
        created_at=pkg.created_at,
        updated_at=pkg.updated_at,
        documents=[CompanyDocumentResponse.model_validate(d, from_attributes=True) for d in docs]
    )

@package_router.delete("/{pkg_id}/documents")
async def remove_package_documents(
    pkg_id: uuid.UUID,
    payload: PackageDocumentUpdate,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    res = await db.execute(select(Package).where(Package.id == pkg_id, Package.business_id == business.id))
    pkg = res.scalar_one_or_none()
    
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
        
    res = await db.execute(select(PackageDocument).where(
        PackageDocument.package_id == pkg_id,
        PackageDocument.document_id.in_(payload.document_ids)
    ))
    pds = res.scalars().all()
    
    for pd in pds:
        await db.delete(pd)
        
    await db.commit()
    
    return {"message": "Documents removed from package"}
