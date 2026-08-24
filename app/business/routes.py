import logging
import os
import uuid
import hashlib
import io
from datetime import datetime, timedelta
from typing import Optional, List
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
# pyrefly: ignore [missing-import]
from sqlalchemy import select
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_session_user, require_role
from app.auth.model import User
from app.database.connection import get_db

# pyrefly: ignore [missing-import]
import pypdf
from app.ai.llm import gemini_service
from app.business.models import (
    GeneralInfo,
    LeadershipInfo,
    FinancialInfo,
    BusinessVerification,
    BusinessVerificationDocument,
)
from app.business.invite_model import TeamInvite
from app.business.invite_service import generate_invite_token, generate_invite_email, create_invite_audit_log
from app.business.schemas import (
    GeneralInfoSaveSchema,
    LeadershipInfoSaveSchema,
    FinancialInfoSaveSchema,
    DocumentResponseSchema,
    BusinessOnboardingFullResponse,
    GeneralInfoResponseSchema,
    LeadershipInfoResponseSchema,
    TeamInviteSaveSchema,
    TeamInviteResponseSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/business/onboarding", tags=["business-onboarding"])

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads", "business_docs")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def calculate_completion_percentage(
    gen: Optional[GeneralInfo],
    info: Optional[LeadershipInfo],
    fin: Optional[FinancialInfo],
    docs: List[BusinessVerificationDocument]
) -> float:
    """Calculate overall onboarding completion percentage."""
    if not gen:
        return 0.0

    total_weight = 100.0
    score = 0.0

    # Step 1: General Info (40%)
    step1_fields = [
        gen.company_name, gen.business_category, gen.business_type,
        gen.business_pan, gen.registered_address, gen.state, gen.city,
        gen.pincode, gen.official_email, gen.official_phone
    ]
    step1_filled = sum(1 for f in step1_fields if f and (str(f).strip() if isinstance(f, str) else True))
    score += (step1_filled / len(step1_fields)) * 40.0

    # Step 2: Business Info (20%)
    if info:
        step2_fields = [info.founder_ceo_name, info.business_model, info.primary_product_service]
        step2_filled = sum(1 for f in step2_fields if f)
        score += (step2_filled / len(step2_fields)) * 20.0

    # Step 3: Financial Info (20%)
    if fin:
        step3_fields = [fin.primary_bank, fin.number_of_accounts, fin.accounting_software]
        step3_filled = sum(1 for f in step3_fields if f is not None)
        score += (step3_filled / len(step3_fields)) * 20.0

    # Step 4: Business Verification Mandatory Docs (20%)
    mandatory_doc_types = {"business_pan", "registration_proof"}
    uploaded_mandatory = sum(1 for d in docs if d.document_type in mandatory_doc_types)
    score += (uploaded_mandatory / len(mandatory_doc_types)) * 20.0

    return min(100.0, round(score, 1))


async def get_or_fetch_user_business(
    user: User, db: AsyncSession
) -> Optional[GeneralInfo]:
    """Helper to retrieve user's BusinessGeneralInfo entity."""
    if user.business_id:
        res = await db.execute(select(GeneralInfo).where(GeneralInfo.id == user.business_id))
        gen = res.scalar_one_or_none()
        if gen:
            return gen



    return None


async def build_full_onboarding_response(
    gen: Optional[GeneralInfo], db: AsyncSession
) -> BusinessOnboardingFullResponse:
    if not gen:
        return BusinessOnboardingFullResponse(
            business_id=None,
            current_step=1,
            completion_percentage=0.0,
            onboarding_completed=False,
            verification_status="pending",
            documents=[],
        )

    # Fetch relations
    info_res = await db.execute(select(LeadershipInfo).where(LeadershipInfo.business_id == gen.id))
    info = info_res.scalar_one_or_none()

    fin_res = await db.execute(select(FinancialInfo).where(FinancialInfo.business_id == gen.id))
    fin = fin_res.scalar_one_or_none()

    ver_res = await db.execute(select(BusinessVerification).where(BusinessVerification.business_id == gen.id))
    ver = ver_res.scalar_one_or_none()

    docs_res = await db.execute(select(BusinessVerificationDocument).where(BusinessVerificationDocument.business_id == gen.id))
    docs = list(docs_res.scalars().all())

    invites_res = await db.execute(select(TeamInvite).where(TeamInvite.business_id == gen.id))
    invites = list(invites_res.scalars().all())

    pct = calculate_completion_percentage(gen, info, fin, docs)
    gen.completion_percentage = pct
    await db.flush()

    gen_schema = GeneralInfoResponseSchema(
        company_name=gen.company_name,
        business_category=gen.business_category,
        business_type=gen.business_type,
        cin=gen.cin,
        gstin=gen.gstin,
        business_pan=gen.business_pan,
        udyam_number=gen.udyam_number,
        date_of_incorporation=gen.date_of_incorporation,
        registered_address=gen.registered_address,
        operational_address=gen.operational_address,
        state=gen.state,
        city=gen.city,
        pincode=gen.pincode,
        website=gen.website,
        official_email=gen.official_email,
        official_phone=gen.official_phone,
    ) if gen else None

    info_schema = LeadershipInfoResponseSchema(
        founder_ceo_name=info.founder_ceo_name,
        founder_ceo_email=info.founder_ceo_email,
        founder_ceo_phone=info.founder_ceo_phone,
        founder_ceo_designation=info.founder_ceo_designation,
        number_of_employees=info.number_of_employees,
        number_of_branches=info.number_of_branches,
        business_model=info.business_model,
        primary_product_service=info.primary_product_service,
        business_description=info.business_description,
        
        cfo_name=info.cfo_name,
        cfo_email=info.cfo_email,
        cfo_phone=info.cfo_phone,
        cfo_designation=info.cfo_designation,
        invite_cfo=info.invite_cfo,
        
        hr_name=info.hr_name,
        hr_email=info.hr_email,
        hr_phone=info.hr_phone,
        hr_designation=info.hr_designation,
        invite_hr=info.invite_hr,
    ) if info else None

    fin_schema = FinancialInfoSaveSchema(
        primary_bank=fin.primary_bank,
        number_of_accounts=fin.number_of_accounts,
        has_business_loan=fin.has_business_loan,
        has_business_credit_card=fin.has_business_credit_card,
        accounting_software=fin.accounting_software,
        digital_payment_methods=fin.digital_payment_methods or [],
    ) if fin else None

    doc_schemas = [
        DocumentResponseSchema.model_validate(d) for d in docs
    ]
    
    invite_schemas = [
        TeamInviteResponseSchema.model_validate(i) for i in invites
    ]

    return BusinessOnboardingFullResponse(
        business_id=gen.id,
        current_step=gen.current_step,
        completion_percentage=pct,
        onboarding_completed=gen.onboarding_completed,
        general_info=gen_schema,
        leadership_info=info_schema,
        financial_info=fin_schema,
        verification_status=ver.verification_status if ver else "pending",
        documents=doc_schemas,
        team_invites=invite_schemas,
    )


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.get("/me", response_model=BusinessOnboardingFullResponse, summary="Get current user's business onboarding state")
async def get_my_business_onboarding(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    gen = await get_or_fetch_user_business(current_user, db)
    return await build_full_onboarding_response(gen, db)


@router.post("/step/1", response_model=BusinessOnboardingFullResponse, summary="Save Step 1 General Information")
async def save_step1_general_info(
    payload: GeneralInfoSaveSchema,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    gen = await get_or_fetch_user_business(current_user, db)

    if not gen:
        gen = GeneralInfo(
            id=uuid.uuid4(),

            company_name=payload.company_name.strip(),
            business_category=payload.business_category,
            business_type=payload.business_type,
            cin=payload.cin.strip() if payload.cin else None,
            gstin=payload.gstin.strip().upper() if payload.gstin else None,
            business_pan=payload.business_pan.strip().upper(),
            udyam_number=payload.udyam_number.strip() if payload.udyam_number else None,
            date_of_incorporation=payload.date_of_incorporation,
            registered_address=payload.registered_address.strip(),
            operational_address=payload.operational_address.strip() if payload.operational_address else None,
            state=payload.state,
            city=payload.city.strip(),
            pincode=payload.pincode.strip(),
            website=payload.website.strip() if payload.website else None,
            official_email=payload.official_email,
            official_phone=payload.official_phone.strip(),
            current_step=1,
        )
        db.add(gen)
        await db.flush()

        current_user.business_id = gen.id

    else:
        gen.company_name = payload.company_name.strip()
        gen.business_category = payload.business_category
        gen.business_type = payload.business_type
        gen.cin = payload.cin.strip() if payload.cin else None
        gen.gstin = payload.gstin.strip().upper() if payload.gstin else None
        gen.business_pan = payload.business_pan.strip().upper()
        gen.udyam_number = payload.udyam_number.strip() if payload.udyam_number else None
        gen.date_of_incorporation = payload.date_of_incorporation
        gen.registered_address = payload.registered_address.strip()
        gen.operational_address = payload.operational_address.strip() if payload.operational_address else None
        gen.state = payload.state
        gen.city = payload.city.strip()
        gen.pincode = payload.pincode.strip()
        gen.website = payload.website.strip() if payload.website else None
        gen.official_email = payload.official_email
        gen.official_phone = payload.official_phone.strip()
        gen.current_step = max(gen.current_step, 1)

    await db.flush()
    return await build_full_onboarding_response(gen, db)


@router.post("/step/2", response_model=BusinessOnboardingFullResponse, summary="Save Step 2 Leadership & Organization")
async def save_step2_team_members(
    payload: LeadershipInfoSaveSchema,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    gen = await get_or_fetch_user_business(current_user, db)
    if not gen:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please complete Step 1 (General Information) first."
        )

    # Save Leadership Info
    info_res = await db.execute(select(LeadershipInfo).where(LeadershipInfo.business_id == gen.id))
    info = info_res.scalar_one_or_none()
    if not info:
        info = LeadershipInfo(
            business_id=gen.id,
            founder_ceo_name=payload.founder_ceo_name,
            founder_ceo_email=payload.founder_ceo_email,
            founder_ceo_phone=payload.founder_ceo_phone,
            founder_ceo_designation=payload.founder_ceo_designation,
            number_of_employees=payload.number_of_employees,
            number_of_branches=payload.number_of_branches,
            business_model=payload.business_model,
            primary_product_service=payload.primary_product_service,
            business_description=payload.business_description,
            
            cfo_name=payload.cfo_name,
            cfo_email=payload.cfo_email,
            cfo_phone=payload.cfo_phone,
            cfo_designation=payload.cfo_designation,
            invite_cfo=payload.invite_cfo,
            
            hr_name=payload.hr_name,
            hr_email=payload.hr_email,
            hr_phone=payload.hr_phone,
            hr_designation=payload.hr_designation,
            invite_hr=payload.invite_hr,
        )
        db.add(info)
    else:
        info.founder_ceo_name = payload.founder_ceo_name
        info.founder_ceo_email = payload.founder_ceo_email
        info.founder_ceo_phone = payload.founder_ceo_phone
        info.founder_ceo_designation = payload.founder_ceo_designation
        info.number_of_employees = payload.number_of_employees
        info.number_of_branches = payload.number_of_branches
        info.business_model = payload.business_model
        info.primary_product_service = payload.primary_product_service
        info.business_description = payload.business_description
        
        info.cfo_name = payload.cfo_name
        info.cfo_email = payload.cfo_email
        info.cfo_phone = payload.cfo_phone
        info.cfo_designation = payload.cfo_designation
        info.invite_cfo = payload.invite_cfo
        
        info.hr_name = payload.hr_name
        info.hr_email = payload.hr_email
        info.hr_phone = payload.hr_phone
        info.hr_designation = payload.hr_designation
        info.invite_hr = payload.invite_hr

    roles_to_invite = []
    if payload.invite_cfo and payload.cfo_email and payload.cfo_name:
        roles_to_invite.append(("cfo", payload.cfo_name, payload.cfo_email, None))
    if payload.invite_hr and payload.hr_email and payload.hr_name:
        roles_to_invite.append(("hr", payload.hr_name, payload.hr_email, None))

    for role, name, email, add_info in roles_to_invite:
        # Check if invite exists
        res = await db.execute(select(TeamInvite).where(
            TeamInvite.business_id == gen.id, TeamInvite.role == role
        ))
        invite = res.scalar_one_or_none()

        if not invite:
            invite = TeamInvite(
                business_id=gen.id,
                invited_by_user_id=current_user.id,
                role=role,
                full_name=name.strip(),
                email=email,
                additional_info=add_info,
                invite_token=generate_invite_token(),
                status="pending"
            )
            db.add(invite)
        else:
            # Update existing if it's pending
            if invite.status == "pending":
                invite.full_name = name.strip()
                invite.email = email
                invite.additional_info = add_info
                # Re-generate token
                invite.invite_token = generate_invite_token()

        await db.flush()
        
        # Send email if pending
        if invite.status == "pending":
            await generate_invite_email(email, name, role, invite.invite_token, gen.company_name)
            await create_invite_audit_log(
                db=db,
                invite_id=invite.id,
                business_id=gen.id,
                actor_user_id=current_user.id,
                action="send",
                target_email=email,
                details={"role": role}
            )

    gen.current_step = max(gen.current_step, 2)
    await db.flush()
    return await build_full_onboarding_response(gen, db)

@router.post("/resend-invite/{invite_id}", summary="Resend an invite")
async def resend_invite(
    invite_id: uuid.UUID,
    current_user: User = Depends(require_role("ceo", "admin")),
    db: AsyncSession = Depends(get_db),
):
    gen = await get_or_fetch_user_business(current_user, db)
    if not gen:
        raise HTTPException(status_code=400, detail="Business not found")
        
    res = await db.execute(select(TeamInvite).where(TeamInvite.id == invite_id, TeamInvite.business_id == gen.id))
    invite = res.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
        
    if invite.status == "accepted":
        raise HTTPException(status_code=400, detail="Invite already accepted")
    if invite.status == "removed":
        raise HTTPException(
            status_code=400,
            detail="Cannot resend invite for a removed member. Please create a new invitation."
        )
        
    now = datetime.utcnow()
    invite.invite_token = generate_invite_token()
    invite.status = "pending"
    invite.expires_at = now + timedelta(hours=24)
    invite.updated_at = now
    await db.flush()
    
    await generate_invite_email(invite.email, invite.full_name, invite.role, invite.invite_token, gen.company_name)
    
    await create_invite_audit_log(
        db=db,
        invite_id=invite.id,
        business_id=gen.id,
        actor_user_id=current_user.id,
        action="resend",
        target_email=invite.email,
    )
    
    return {"status": "success", "message": "Invite resent"}

@router.get("/invites", summary="Get all invites")
async def get_team_invites(
    current_user: User = Depends(require_role("ceo", "admin")),
    db: AsyncSession = Depends(get_db),
):
    gen = await get_or_fetch_user_business(current_user, db)
    if not gen:
        return []
    
    res = await db.execute(select(TeamInvite).where(TeamInvite.business_id == gen.id))
    invites = res.scalars().all()
    
    return [TeamInviteResponseSchema.model_validate(i) for i in invites]


@router.post("/step/3", response_model=BusinessOnboardingFullResponse, summary="Save Step 3 Financial Information")
async def save_step3_financial_info(
    payload: FinancialInfoSaveSchema,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    gen = await get_or_fetch_user_business(current_user, db)
    if not gen:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please complete Step 1 (General Information) first."
        )

    fin_res = await db.execute(select(FinancialInfo).where(FinancialInfo.business_id == gen.id))
    fin = fin_res.scalar_one_or_none()

    if not fin:
        fin = FinancialInfo(
            business_id=gen.id,
            primary_bank=payload.primary_bank.strip() if payload.primary_bank else None,
            number_of_accounts=payload.number_of_accounts,
            has_business_loan=payload.has_business_loan,
            has_business_credit_card=payload.has_business_credit_card,
            accounting_software=payload.accounting_software,
            digital_payment_methods=payload.digital_payment_methods or [],
        )
        db.add(fin)
    else:
        fin.primary_bank = payload.primary_bank.strip() if payload.primary_bank else None
        fin.number_of_accounts = payload.number_of_accounts
        fin.has_business_loan = payload.has_business_loan
        fin.has_business_credit_card = payload.has_business_credit_card
        fin.accounting_software = payload.accounting_software
        fin.digital_payment_methods = payload.digital_payment_methods or []

    gen.current_step = max(gen.current_step, 3)
    await db.flush()
    return await build_full_onboarding_response(gen, db)


@router.post("/documents/upload", summary="Upload Business Verification Document")
async def upload_verification_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    document_category: str = Form("mandatory"),
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    gen = await get_or_fetch_user_business(current_user, db)
    if not gen:
        # Create skeleton profile since document upload is now Step 1
        gen = GeneralInfo(
            id=uuid.uuid4(),

            company_name="",
            business_category="Others",
            business_type="Private Limited",
            business_pan="",
            registered_address="",
            state="",
            city="",
            pincode="",
            official_email=current_user.email or "",
            official_phone="",
            current_step=1,
        )
        db.add(gen)
        await db.flush()
        
        current_user.business_id = gen.id


    # Directory for this business
    biz_dir = os.path.join(UPLOAD_DIR, str(gen.id))
    os.makedirs(biz_dir, exist_ok=True)

    file_ext = os.path.splitext(file.filename)[1]
    safe_filename = f"{document_type}_{uuid.uuid4().hex[:8]}{file_ext}"
    file_path = os.path.join(biz_dir, safe_filename)

    file_bytes = await file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    logger.info(f"==> Document upload received: '{file.filename}' (type: {document_type}, category: {document_category}, size: {len(file_bytes)} bytes)")

    # 0. File type validation — only PDF accepted (quality score requires text extraction)
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file.content_type}'. Only PDF files are accepted for document verification."
        )

    # 1. Duplication Check — Global (same file hash across ANY business)
    logger.info(f"  [1/4] Checking for duplicate documents globally (hash: {file_hash[:12]}...)...")
    duplicate_res = await db.execute(
        select(BusinessVerificationDocument).where(
            BusinessVerificationDocument.file_hash == file_hash
        )
    )
    existing_duplicate = duplicate_res.scalar_one_or_none()
    if existing_duplicate:
        is_same_business = existing_duplicate.business_id == gen.id
        if is_same_business:
            logger.warning(f"  [DUPLICATE] Document upload rejected — same file already uploaded for this business (doc_id: {existing_duplicate.id}).")
            raise HTTPException(status_code=400, detail="Duplicate document uploaded. This file has already been uploaded for your business.")
        else:
            logger.warning(f"  [DUPLICATE] Document upload rejected — same file already uploaded by another business (business_id: {existing_duplicate.business_id}, doc_id: {existing_duplicate.id}).")
            raise HTTPException(status_code=400, detail="Duplicate document detected. This exact file has already been uploaded by another business account.")

    # 2. Extract Text (if PDF)
    document_text = ""
    if file.content_type == "application/pdf":
        logger.info("  [2/4] Extracting text from PDF for AI verification...")
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    document_text += text + "\n"
            logger.info(f"  [2/4] Extracted {len(document_text)} characters from {len(reader.pages)} page(s).")
        except Exception as e:
            logger.warning(f"  [2/4] Failed to extract text from PDF: {e}")
    else:
        logger.info(f"  [2/4] Non-PDF file ({file.content_type}), skipping text extraction.")

    # 3. Quality & Verification Check via AI
    quality_score = None
    is_verified = False
    verification_notes = None

    if document_text.strip():
        expected_id = gen.business_pan if document_type == "business_pan" else (gen.cin if document_type == "registration_proof" else "")
        logger.info(f"  [3/4] Running AI verification (type: {document_type}, expected_id: {expected_id or 'N/A'})...")
        verification_result = await gemini_service.verify_document_quality(document_text, document_type, expected_id or "")
        
        if verification_result:
            is_readable = verification_result.get("is_readable", False)
            quality_score = verification_result.get("quality_score", 0.0)
            extracted_id = verification_result.get("extracted_id")
            verification_notes = verification_result.get("notes", "")
            
            logger.info(f"  [3/4] AI Verification Result — Readable: {is_readable}, Quality: {quality_score}, Extracted ID: {extracted_id}, Notes: {verification_notes}")
            
            if not is_readable or quality_score < 50.0:
                logger.warning(f"  [REJECTED] Document quality too low (Score: {quality_score}). Rejecting upload.")
                raise HTTPException(status_code=400, detail=f"Document quality is too low (Score: {quality_score}). Notes: {verification_notes}")
                
            if expected_id and extracted_id and expected_id.upper() not in extracted_id.upper():
                logger.warning(f"  [REJECTED] ID mismatch — Expected: {expected_id}, Found: {extracted_id}. Rejecting upload.")
                raise HTTPException(status_code=400, detail=f"Document verification failed. Expected ID {expected_id} but found {extracted_id}.")
                
            is_verified = True
            logger.info(f"  [3/4] ✅ Document VERIFIED successfully (quality: {quality_score}%).")
        else:
            logger.warning("  [3/4] AI verification returned no result. Document will require manual review.")
            verification_notes = "AI verification unavailable. Manual verification required."
    else:
        logger.info("  [3/4] No text extracted from document. Marking for manual verification.")
        verification_notes = "No text extracted. Manual verification required."

    logger.info(f"  [4/4] Saving file to disk and persisting to database...")
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # Check if doc of this document_type already exists
    existing_res = await db.execute(
        select(BusinessVerificationDocument).where(
            BusinessVerificationDocument.business_id == gen.id,
            BusinessVerificationDocument.document_type == document_type
        )
    )
    existing_doc = existing_res.scalar_one_or_none()

    if existing_doc:
        # Replace existing file
        if os.path.exists(existing_doc.file_path):
            try:
                os.remove(existing_doc.file_path)
            except Exception as e:
                logger.warning(f"Failed to remove old file {existing_doc.file_path}: {e}")

        existing_doc.filename = safe_filename
        existing_doc.original_name = file.filename
        existing_doc.file_path = file_path
        existing_doc.file_size_bytes = len(file_bytes)
        existing_doc.mime_type = file.content_type or "application/octet-stream"
        existing_doc.document_category = document_category
        existing_doc.upload_status = "uploaded"
        existing_doc.file_hash = file_hash
        existing_doc.quality_score = quality_score
        existing_doc.is_verified = is_verified
        existing_doc.verification_notes = verification_notes
    else:
        new_doc = BusinessVerificationDocument(
            business_id=gen.id,
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
            verification_notes=verification_notes
        )
        db.add(new_doc)

    # Ensure BusinessVerification entity exists
    ver_res = await db.execute(select(BusinessVerification).where(BusinessVerification.business_id == gen.id))
    ver = ver_res.scalar_one_or_none()
    if not ver:
        ver = BusinessVerification(
            business_id=gen.id,
            verification_status="pending",
        )
        db.add(ver)

    gen.current_step = max(gen.current_step, 4)
    await db.flush()

    return await build_full_onboarding_response(gen, db)


@router.delete("/documents/{doc_id}", summary="Delete an uploaded verification document")
async def delete_verification_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    gen = await get_or_fetch_user_business(current_user, db)
    if not gen:
        raise HTTPException(status_code=404, detail="Business profile not found.")

    doc_res = await db.execute(
        select(BusinessVerificationDocument).where(
            BusinessVerificationDocument.id == doc_id,
            BusinessVerificationDocument.business_id == gen.id
        )
    )
    doc = doc_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception as e:
            logger.warning(f"Could not remove file {doc.file_path}: {e}")

    await db.delete(doc)
    await db.flush()

    return await build_full_onboarding_response(gen, db)


@router.post("/step/extract-from-docs", summary="Extract Business Info from Uploaded Documents")
async def extract_business_info_from_docs(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    gen = await get_or_fetch_user_business(current_user, db)
    if not gen:
        raise HTTPException(status_code=400, detail="No business profile found. Please upload documents first.")

    # Get documents
    docs_res = await db.execute(select(BusinessVerificationDocument).where(BusinessVerificationDocument.business_id == gen.id))
    docs = docs_res.scalars().all()

    combined_text = ""
    for doc in docs:
        if doc.file_path.lower().endswith(".pdf") and os.path.exists(doc.file_path):
            try:
                reader = pypdf.PdfReader(doc.file_path)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        combined_text += text + "\n"
            except Exception as e:
                logger.warning(f"Failed to extract text from {doc.file_path}: {e}")

    if not combined_text.strip():
        # Fallback if no text extracted (e.g. image files)
        return {"status": "no_text_extracted", "data": None}

    extracted_data = await gemini_service.extract_business_registration_data(combined_text)
    if extracted_data:
        return {"status": "success", "data": extracted_data}
    else:
        return {"status": "extraction_failed", "data": None}

@router.post("/complete", summary="Complete Business Onboarding")
async def complete_business_onboarding(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    gen = await get_or_fetch_user_business(current_user, db)
    if not gen:
        raise HTTPException(status_code=400, detail="Business onboarding profile not initialized.")

    gen.onboarding_completed = True
    gen.current_step = 5
    gen.completion_percentage = 100.0

    ver_res = await db.execute(select(BusinessVerification).where(BusinessVerification.business_id == gen.id))
    ver = ver_res.scalar_one_or_none()
    if not ver:
        ver = BusinessVerification(business_id=gen.id, verification_status="completed", is_verified=True, verified_at=datetime.utcnow())
        db.add(ver)
    else:
        ver.verification_status = "completed"



    if current_user.role == "user":
        current_user.role = "ceo"

    await db.flush()
    logger.info(f"Business onboarding completed for business_id {gen.id} (user_id: {current_user.id}).")

    return {
        "status": "success",
        "message": "Business onboarding successfully completed!",
        "redirect_to": "/home"
    }
