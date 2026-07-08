import os
import uuid
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete

from app.database.connection import get_db
from app.database.repository import BaseRepository
from app.database.models import Account, ProcessingMetadata, Transaction
from app.statement.review.validator import StatementValidator
from app.storage.file_manager import file_manager
from app.statement.service import StatementProcessingService
from app.statement.model import (
    DocumentResponse, DocumentStatus,
    AccountResponse, TransactionResponse, TransactionListResponse,
    ExtractedStatementResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/statements", tags=["Statements"])

@router.post("/upload", response_model=DocumentResponse)
async def upload_single_statement(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    person_id: Optional[str] = Query(None, description="The user/person ID associating this statement"),
    db: AsyncSession = Depends(get_db)
):
    """
    Uploads a single PDF statement.
    Validates file integrity, checks for duplicate upload, saves file locally,
    and runs the extraction pipeline in the background.
    """
    logger.info(f"==> Received single upload request for file: {file.filename}")
    
    # 1. Format validation
    StatementValidator.validate_file(file)
    logger.info("  [1/6] Format validation successful.")
    
    # 2. Content integrity check & Hash calculation for deduplication
    md5_hash = await StatementValidator.validate_content_and_get_hash(file)
    logger.info(f"  [2/6] File content integrity check passed. Calculated MD5: {md5_hash}")
    
    document_repo = BaseRepository(db, "documents")
    
    # Check duplicate matching hash
    logger.info("  [3/6] Checking for duplicate document uploads in the database...")
    existing = await document_repo.find({"hash_md5": md5_hash})
    if existing:
        logger.warning(f"  [CONFLICT] File upload rejected. Duplicate document found (Document ID: {existing[0].id}).")
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate statement detected. File has already been uploaded (Document ID: {existing[0].id})."
        )
    
    # 3. Retrieve size
    await file.seek(0)
    content = await file.read()
    file_size = len(content)
    await file.seek(0)
    
    # 3b. Setup / Verify Person record association (with default fallback for offline/no-auth testing)
    person_repo = BaseRepository(db, "persons")
    
    if person_id:
        person = await person_repo.get_by_id(person_id)
        if not person:
            try:
                p_uuid = uuid.UUID(person_id)
                await person_repo.create({
                    "id": p_uuid,
                    "email": f"user_{person_id[:8]}@example.com",
                    "full_name": f"User {person_id[:8]}",
                    "created_at": datetime.utcnow()
                })
            except Exception:
                person_id = None
                
    if not person_id:
        default_uuid = uuid.UUID("00000000-0000-0000-0000-000000000000")
        existing_default = await person_repo.get_by_id(str(default_uuid))
        if not existing_default:
            await person_repo.create({
                "id": default_uuid,
                "email": "default@example.com",
                "full_name": "Default User",
                "created_at": datetime.utcnow()
            })
        person_id = str(default_uuid)

    person_uuid = uuid.UUID(person_id)
    
    # 4. Save document record in database
    doc_data = {
        "person_id": person_uuid,
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
    logger.info(f"  [4/6] Created document record in database. Generated UUID: {doc_id}")
    
    # Commit immediately so the background task can query/see this document!
    await db.commit()
    logger.info("  [5/6] Committed database transaction for document initialization.")
    
    # 5. Save the file to local storage
    file_path = file_manager.save_file(doc_id, file)
    logger.info(f"  [6/6] Saved PDF locally to path: {file_path}")
    
    # 6. Dispatch processing task to background thread pool
    logger.info(f"==> Dispatching extraction pipeline to background queue. Document ID: {doc_id}")
    background_tasks.add_task(StatementProcessingService.process_statement_task, doc_id, file_path, person_id)
    
    # Fetch database record to return standard Pydantic response
    doc_record = await document_repo.get_by_id(doc_id)
    return doc_record

@router.post("/upload/bulk")
async def upload_bulk_statements(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    person_id: Optional[str] = Query(None, description="The user/person ID associating these statements"),
    db: AsyncSession = Depends(get_db)
):
    """
    Uploads multiple PDF statements.
    Processes each document asynchronously, returning success and failure logs.
    """
    # Setup / Verify Person record association (with default fallback for offline/no-auth testing)
    person_repo = BaseRepository(db, "persons")
    
    if person_id:
        person = await person_repo.get_by_id(person_id)
        if not person:
            try:
                p_uuid = uuid.UUID(person_id)
                await person_repo.create({
                    "id": p_uuid,
                    "email": f"user_{person_id[:8]}@example.com",
                    "full_name": f"User {person_id[:8]}",
                    "created_at": datetime.utcnow()
                })
            except Exception:
                person_id = None
                
    if not person_id:
        default_uuid = uuid.UUID("00000000-0000-0000-0000-000000000000")
        existing_default = await person_repo.get_by_id(str(default_uuid))
        if not existing_default:
            await person_repo.create({
                "id": default_uuid,
                "email": "default@example.com",
                "full_name": "Default User",
                "created_at": datetime.utcnow()
            })
        person_id = str(default_uuid)

    person_uuid = uuid.UUID(person_id)
    uploaded = []
    errors = []
    document_repo = BaseRepository(db, "documents")
    
    for file in files:
        try:
            StatementValidator.validate_file(file)
            md5_hash = await StatementValidator.validate_content_and_get_hash(file)
            
            existing = await document_repo.find({"hash_md5": md5_hash})
            if existing:
                errors.append({
                    "filename": file.filename,
                    "error": "Duplicate file detected. Already uploaded."
                })
                continue
                
            await file.seek(0)
            content = await file.read()
            file_size = len(content)
            await file.seek(0)
            
            doc_data = {
                "person_id": person_uuid,
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
            
            # Commit immediately so the background task can query/see this document!
            await db.commit()
            
            file_path = file_manager.save_file(doc_id, file)
            background_tasks.add_task(StatementProcessingService.process_statement_task, doc_id, file_path, person_id)
            
            uploaded.append({
                "document_id": doc_id,
                "filename": file.filename,
                "status": DocumentStatus.PENDING
            })
        except Exception as e:
            errors.append({
                "filename": file.filename,
                "error": str(e)
            })
            
    return {"uploaded": uploaded, "errors": errors}

@router.get("", response_model=List[DocumentResponse])
async def get_uploaded_documents(db: AsyncSession = Depends(get_db)):
    """Fetch list of all uploaded documents."""
    document_repo = BaseRepository(db, "documents")
    docs = await document_repo.find({}, limit=100)
    return docs

@router.get("/{id}/status")
async def get_processing_status(id: str, db: AsyncSession = Depends(get_db)):
    """Check the status and processing stage logs of a statement."""
    try:
        doc_uuid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Document ID format.")
        
    document_repo = BaseRepository(db, "documents")
    doc = await document_repo.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    # Query metadata logs
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

@router.get("/{id}/extracted", response_model=ExtractedStatementResponse)
async def get_extracted_statement(id: str, db: AsyncSession = Depends(get_db)):
    """Fetch the document details, parsed account info, and transactions."""
    try:
        doc_uuid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Document ID format.")
        
    document_repo = BaseRepository(db, "documents")
    doc = await document_repo.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    
    # Query account information
    account_repo = BaseRepository(db, "accounts")
    accounts = await account_repo.find({"document_id": id})
    account = accounts[0] if accounts else None
    
    # Query transactions
    transaction_repo = BaseRepository(db, "transactions")
    txs = await transaction_repo.find({"document_id": id})
    
    return {
        "document": doc,
        "account": account,
        "transactions": txs
    }

@router.get("/{id}/transactions", response_model=TransactionListResponse)
async def get_transactions_by_statement_id(
    id: str,
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Fetch transactions for a statement with support for pagination."""
    try:
        doc_uuid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Document ID format.")
        
    transaction_repo = BaseRepository(db, "transactions")
    
    # Get total count
    from sqlalchemy import func, select
    stmt = select(func.count(Transaction.id)).where(Transaction.document_id == doc_uuid)
    result = await db.execute(stmt)
    total = result.scalar() or 0
    
    txs = await transaction_repo.find({"document_id": id}, limit=limit, skip=skip)
    
    return {
        "total": total,
        "transactions": txs
    }

@router.post("/{id}/reprocess", response_model=DocumentResponse)
async def reprocess_statement(
    id: str,
    background_tasks: BackgroundTasks,
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
        
    # Check if local file exists
    file_extension = os.path.splitext(doc.filename)[1] or ".pdf"
    filename = f"{id}{file_extension}"
    if not file_manager.file_exists(filename):
        raise HTTPException(status_code=400, detail="Stored PDF file not found. Reprocessing failed.")
        
    file_path = file_manager.get_file_path(filename)
    
    # 1. Delete associated data before reprocessing (cascade will purge transactions)
    await db.execute(delete(Account).where(Account.document_id == doc_uuid))
    await db.execute(delete(ProcessingMetadata).where(ProcessingMetadata.document_id == doc_uuid))
    
    # 2. Reset document record status to PENDING
    await document_repo.update(id, {
        "status": DocumentStatus.PENDING,
        "error_message": None,
        "updated_at": datetime.utcnow()
    })
    
    # We commit changes to db before starting background task
    await db.commit()
    
    # 3. Add to background pipeline task
    person_id_str = str(doc.person_id) if doc.person_id else None
    background_tasks.add_task(StatementProcessingService.process_statement_task, id, file_path, person_id_str)
    
    return doc

@router.delete("/{id}")
async def delete_uploaded_statement(id: str, db: AsyncSession = Depends(get_db)):
    """
    Cascades delete for statement.
    Deletes PDF from file system, and removes document, accounts, transactions, 
    and processing telemetry from PostgreSQL database.
    """
    try:
        doc_uuid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Document ID format.")
        
    document_repo = BaseRepository(db, "documents")
    doc = await document_repo.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    # 1. Remove file from storage
    file_extension = os.path.splitext(doc.filename)[1] or ".pdf"
    filename = f"{id}{file_extension}"
    file_manager.delete_file(filename)
    
    # 2. Cascade delete document (PostgreSQL cascade deletes account, transactions, and metadata automatically)
    await document_repo.delete(id)
    
    return {"message": "Statement and all associated accounts, transactions, and logs deleted successfully."}
