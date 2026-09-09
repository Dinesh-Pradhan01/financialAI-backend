import os
import uuid
import logging
import asyncio
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from app.database.connection import get_db
from app.database.repository import BaseRepository
from app.database.models import Transaction, Account, ProcessingMetadata, BankStatementData
from app.auth.dependencies import get_current_session_user
from app.auth.model import User

from app.transaction.review.validator import StatementValidator
from app.storage.file_manager import file_manager
from app.transaction.service import TransactionExtractionService
from app.transaction.schemas import (
    DocumentResponse, DocumentStatus,
    TransactionResponse, TransactionListResponse,
    ExtractedStatementResponse, TransactionUpdateRequest
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transactions", tags=["Transactions"])


# ==========================================
# DOCUMENT UPLOAD & EXTRACTION PIPELINE
# ==========================================

@router.post("/upload", response_model=DocumentResponse)
async def upload_single_statement(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    business_id: Optional[str] = Query(None, description="The business ID associating this statement"),
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Uploads a single PDF statement for transaction extraction.
    """
    logger.info(f"==> Received single upload request for file: {file.filename}")
    
    StatementValidator.validate_file(file)
    md5_hash = await StatementValidator.validate_content_and_get_hash(file)
    
    document_repo = BaseRepository(db, "documents")
    existing = await document_repo.find({"hash_md5": md5_hash})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate statement detected. File has already been uploaded (Document ID: {existing[0].id})."
        )
    
    await file.seek(0)
    content = await file.read()
    file_size = len(content)
    await file.seek(0)
    
    business_repo = BaseRepository(db, "general_info")
    if current_user.role == "admin" and business_id:
        try:
            business_uuid = uuid.UUID(business_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid business_id UUID format.")
        business = await business_repo.get_by_id(str(business_uuid))
        if not business:
            raise HTTPException(status_code=400, detail="Business profile not found for this business_id.")
    else:
        if not current_user.business_id:
            raise HTTPException(status_code=400, detail="No business profile associated with the current user.")
        business_uuid = current_user.business_id

    doc_data = {
        "business_id": business_uuid,
        "filename": file.filename,
        "original_name": file.filename,
        "hash_md5": md5_hash,
        "file_size_bytes": file_size,
        "status": DocumentStatus.PENDING,
        "error_message": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    doc_id = await document_repo.create(doc_data)
    await db.commit()
    
    file_path = file_manager.save_file(doc_id, file)
    
    background_tasks.add_task(
        TransactionExtractionService.extract_transactions_task,
        doc_id,
        file_path,
        str(business_uuid)
    )
    
    doc_record = await document_repo.get_by_id(doc_id)
    return doc_record

@router.post("/upload/bulk")
async def upload_bulk_statements(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    business_id: Optional[str] = Query(None, description="The business ID associating these statements"),
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Uploads multiple PDF statements for transaction extraction.
    """
    business_repo = BaseRepository(db, "general_info")
    if current_user.role == "admin" and business_id:
        try:
            business_uuid = uuid.UUID(business_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid business_id UUID format.")
        business = await business_repo.get_by_id(str(business_uuid))
        if not business:
            raise HTTPException(status_code=400, detail="Business profile not found for this business_id.")
    else:
        if not current_user.business_id:
            raise HTTPException(status_code=400, detail="No business profile associated with the current user.")
        business_uuid = current_user.business_id

    uploaded = []
    errors = []
    document_repo = BaseRepository(db, "documents")
    
    for file in files:
        try:
            StatementValidator.validate_file(file)
            md5_hash = await StatementValidator.validate_content_and_get_hash(file)
            
            existing = await document_repo.find({"hash_md5": md5_hash})
            if existing:
                errors.append({"filename": file.filename, "error": "Duplicate file detected. Already uploaded."})
                continue
                
            await file.seek(0)
            content = await file.read()
            file_size = len(content)
            await file.seek(0)
            
            doc_data = {
                "business_id": business_uuid,
                "filename": file.filename,
                "original_name": file.filename,
                "hash_md5": md5_hash,
                "file_size_bytes": file_size,
                "status": DocumentStatus.PENDING,
                "error_message": None,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            doc_id = await document_repo.create(doc_data)
            await db.commit()
            
            file_path = file_manager.save_file(doc_id, file)
            uploaded.append({"document_id": doc_id, "filename": file.filename, "file_path": file_path})
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})
            
    if uploaded:
        for item in uploaded:
            file_path = item.pop("file_path", None)
            background_tasks.add_task(
                TransactionExtractionService.extract_transactions_task,
                item["document_id"], file_path, str(business_uuid)
            )
            item["status"] = DocumentStatus.PENDING
            
    return {"uploaded": uploaded, "errors": errors}

@router.get("/documents", response_model=List[DocumentResponse])
async def get_uploaded_documents(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetch list of all uploaded transaction documents."""
    document_repo = BaseRepository(db, "documents")
    if current_user.role == "admin":
        docs = await document_repo.find({}, limit=100)
    else:
        if not current_user.business_id:
            return []
        docs = await document_repo.find({"business_id": current_user.business_id}, limit=100)
    return docs

@router.get("/documents/{id}", response_model=DocumentResponse)
async def get_document_by_id(
    id: str,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetch details of a single uploaded document by its ID."""
    try:
        doc_uuid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Document ID format.")
        
    document_repo = BaseRepository(db, "documents")
    doc = await document_repo.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if current_user.role != "admin" and doc.business_id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Access denied to this document.")
        
    return doc

@router.get("/documents/{id}/status")
async def get_processing_status(
    id: str,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db)
):
    """Check the status and processing stage logs of a document."""
    try:
        doc_uuid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Document ID format.")
        
    document_repo = BaseRepository(db, "documents")
    doc = await document_repo.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if current_user.role != "admin" and doc.business_id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Access denied to this document.")
        
    meta_repo = BaseRepository(db, "processing_metadata")
    metas = await meta_repo.find({"document_id": id})
    meta = metas[0] if metas else None
    
    response = {
        "document_id": id,
        "filename": doc.filename,
        "status": doc.status,
        "error_message": doc.error_message,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at
    }
    if meta:
        response["processing_time_seconds"] = meta.processing_time_seconds
        response["model_used"] = meta.model_used
        response["stages_completed"] = meta.stages_completed
        response["logs"] = meta.logs
    return response

@router.get("/documents/{id}/extracted", response_model=ExtractedStatementResponse)
async def get_extracted_statement(
    id: str,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetch the document details, parsed account info, and transactions."""
    try:
        doc_uuid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Document ID format.")
        
    document_repo = BaseRepository(db, "documents")
    doc = await document_repo.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if current_user.role != "admin" and doc.business_id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Access denied to this document.")
    
    account = None
    if doc.account_id:
        account_repo = BaseRepository(db, "accounts")
        account = await account_repo.get_by_id(str(doc.account_id))
    
    stmt_data_repo = BaseRepository(db, "bank_statement_data")
    stmt_data_list = await stmt_data_repo.find({"document_id": id})
    stmt_data = stmt_data_list[0] if stmt_data_list else None
    
    transaction_repo = BaseRepository(db, "transactions")
    txs = await transaction_repo.find({"document_id": id})
    
    return {
        "document": doc,
        "account": account,
        "bank_statement_data": stmt_data,
        "transactions": txs
    }

@router.get("/documents/{id}/transactions", response_model=TransactionListResponse)
async def get_transactions_by_document_id(
    id: str,
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetch transactions for a specific document with support for pagination."""
    try:
        doc_uuid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Document ID format.")
        
    document_repo = BaseRepository(db, "documents")
    doc = await document_repo.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if current_user.role != "admin" and doc.business_id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Access denied to this document.")
        
    transaction_repo = BaseRepository(db, "transactions")
    
    stmt = select(func.count(Transaction.id)).where(Transaction.document_id == doc_uuid)
    result = await db.execute(stmt)
    total = result.scalar() or 0
    
    txs = await transaction_repo.find({"document_id": id}, limit=limit, skip=skip)
    
    return {"total": total, "transactions": txs}

@router.post("/documents/{id}/reprocess", response_model=DocumentResponse)
async def reprocess_statement(
    id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db)
):
    """Retriggers processing on an already uploaded PDF file."""
    try:
        doc_uuid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Document ID format.")
        
    document_repo = BaseRepository(db, "documents")
    doc = await document_repo.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if current_user.role != "admin" and doc.business_id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Access denied to this document.")
        
    file_extension = os.path.splitext(doc.filename)[1] or ".pdf"
    filename = f"{id}{file_extension}"
    if not file_manager.file_exists(filename):
        raise HTTPException(status_code=400, detail="Stored PDF file not found. Reprocessing failed.")
        
    file_path = file_manager.get_file_path(filename)
    
    await db.execute(delete(Transaction).where(Transaction.document_id == doc_uuid))
    await db.execute(delete(BankStatementData).where(BankStatementData.document_id == doc_uuid))
    await db.execute(delete(ProcessingMetadata).where(ProcessingMetadata.document_id == doc_uuid))
    
    await document_repo.update(id, {
        "status": DocumentStatus.PENDING,
        "error_message": None,
        "updated_at": datetime.utcnow()
    })
    
    await db.commit()
    
    business_id_str = str(doc.business_id) if doc.business_id else None
    background_tasks.add_task(
        TransactionExtractionService.extract_transactions_task,
        id, file_path, business_id_str
    )
    
    await db.refresh(doc)
    return doc

@router.delete("/documents/{id}")
async def delete_uploaded_statement(
    id: str,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db)
):
    """Cascades delete for statement."""
    try:
        doc_uuid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Document ID format.")
        
    document_repo = BaseRepository(db, "documents")
    doc = await document_repo.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if current_user.role != "admin" and doc.business_id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Access denied to this document.")
        
    file_extension = os.path.splitext(doc.filename)[1] or ".pdf"
    filename = f"{id}{file_extension}"
    file_manager.delete_file(filename)
    
    await document_repo.delete(id)
    return {"message": "Document and all associated data deleted successfully."}


# ==========================================
# TRANSACTION CRUD (MANUAL)
# ==========================================

@router.get("/account/{account_id}", response_model=TransactionListResponse)
async def get_transactions_by_account(
    account_id: str,
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetch all transactions for a specific persistent bank account."""
    try:
        acc_uuid = uuid.UUID(account_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Account ID format.")
        
    account_repo = BaseRepository(db, "accounts")
    account = await account_repo.get_by_id(account_id)
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")
        
    if current_user.role != "admin" and account.business_id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Access denied to this account's transactions.")
        
    transaction_repo = BaseRepository(db, "transactions")
    
    stmt = select(func.count(Transaction.id)).where(Transaction.account_id == acc_uuid)
    result = await db.execute(stmt)
    total = result.scalar() or 0
    
    txs = await transaction_repo.find({"account_id": account_id}, limit=limit, skip=skip)
    
    return {"total": total, "transactions": txs}

@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction_by_id(
    transaction_id: str,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetch a single transaction by ID."""
    try:
        tx_uuid = uuid.UUID(transaction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Transaction ID format.")
        
    transaction_repo = BaseRepository(db, "transactions")
    tx = await transaction_repo.get_by_id(transaction_id)
    
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
        
    if current_user.role != "admin" and tx.business_id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Access denied to this transaction.")
        
    return tx

@router.put("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: str,
    update_data: TransactionUpdateRequest,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually update a transaction's details.
    """
    try:
        tx_uuid = uuid.UUID(transaction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Transaction ID format.")
        
    transaction_repo = BaseRepository(db, "transactions")
    tx = await transaction_repo.get_by_id(transaction_id)
    
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
        
    if current_user.role != "admin" and tx.business_id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Access denied to this transaction.")
        
    update_dict = update_data.model_dump(exclude_unset=True)
    if not update_dict:
        return tx
        
    update_dict["updated_at"] = datetime.utcnow()
    
    try:
        await transaction_repo.update(transaction_id, update_dict)
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to update transaction {transaction_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error while updating transaction.")
        
    await db.refresh(tx)
    return tx

@router.delete("/{transaction_id}")
async def delete_transaction(
    transaction_id: str,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Permanently delete a single transaction.
    """
    try:
        tx_uuid = uuid.UUID(transaction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Transaction ID format.")
        
    transaction_repo = BaseRepository(db, "transactions")
    tx = await transaction_repo.get_by_id(transaction_id)
    
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
        
    if current_user.role != "admin" and tx.business_id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Access denied to this transaction.")
        
    try:
        await transaction_repo.delete(transaction_id)
    except Exception as e:
        logger.error(f"Failed to delete transaction {transaction_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error while deleting transaction.")
        
    return {"message": "Transaction deleted successfully."}
