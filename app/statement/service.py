import time
import logging
import uuid
import asyncio
from typing import Optional
from datetime import datetime
from app.database.connection import db_manager
from app.config import settings
from app.database.repository import BaseRepository
from app.statement.model import DocumentStatus
from app.statement.extraction.extractor import StatementExtractor
from app.ai.llm import gemini_service
from app.statement.extraction.parser import FallbackStatementParser
from app.statement.extraction.normalizer import StatementNormalizer

logger = logging.getLogger(__name__)

class StatementProcessingService:
    @staticmethod
    async def process_statement_task(document_id: str, file_path: str, person_id: Optional[str] = None):
        """
        Asynchronous background task that orchestrates the entire extraction pipeline:
        1. Read text from PDF.
        2. Recognize bank name, account info, and transactions.
        3. Normalize amounts, references, types, and categories.
        4. Persist to PostgreSQL database.
        5. Write telemetry metrics to processing_metadata.
        """
        logger.info(f"Asynchronous processing started for Document ID: {document_id}")
        start_time = time.time()
        
        # Verify db manager engine has been initialized
        if db_manager.session_factory is None:
            logger.error("PostgreSQL connection session factory not initialized!")
            return

        # 1. Update Document status to PROCESSING immediately in a separate transaction
        async with db_manager.session_factory() as session:
            try:
                document_repo = BaseRepository(session, "documents")
                update_data = {
                    "status": DocumentStatus.PROCESSING,
                    "updated_at": datetime.utcnow()
                }
                if person_id:
                    update_data["person_id"] = uuid.UUID(person_id) if isinstance(person_id, str) else person_id
                await document_repo.update(document_id, update_data)
                await session.commit()
            except Exception as e:
                logger.error(f"Failed to update document status to PROCESSING: {e}")
                return

        stages = ["uploaded", "validated"]
        logs = [f"[{datetime.utcnow().isoformat()}] Pipeline status updated to PROCESSING."]
        model_used = "offline-fallback"
        input_tokens = 0
        output_tokens = 0

        try:
            # 2. Extract raw PDF text page-by-page
            logger.info(f"[{document_id}] Starting PDF text extraction on {file_path}...")
            pages_text = StatementExtractor.extract_pages(file_path)
            pdf_text = "\n".join(pages_text).strip()
            logs.append(f"[{datetime.utcnow().isoformat()}] PyPDF extracted {len(pages_text)} pages successfully ({len(pdf_text)} characters).")
            logger.info(f"[{document_id}] PDF text extraction completed successfully ({len(pages_text)} pages, {len(pdf_text)} characters).")
            stages.append("extracted")

            # 3. Bank Detection & AI Extraction
            extracted_data = None
            if gemini_service.is_available():
                num_pages = len(pages_text)
                if num_pages <= 15:
                    # Single-shot extraction for small-to-medium statements
                    logger.info(f"[{document_id}] PDF has {num_pages} page(s). Dispatching single-shot prompt to Gemini LLM API...")
                    logs.append(f"[{datetime.utcnow().isoformat()}] Dispatching single-shot prompt to Gemini API.")
                    extracted_data = await gemini_service.extract_statement_data(pdf_text)
                    if extracted_data:
                        metrics = extracted_data.get("_metrics", {})
                        model_used = metrics.get("model_used", settings.GEMINI_MODEL)
                        input_tokens = metrics.get("input_tokens", 0)
                        output_tokens = metrics.get("output_tokens", 0)
                        logs.append(f"[{datetime.utcnow().isoformat()}] Gemini API successfully extracted structured data. Model: {model_used}.")
                        logger.info(f"[{document_id}] Gemini LLM single-shot extraction successful.")
                        stages.append("detected")
                else:
                    # Page-chunked extraction for multi-page statements (larger than 15 pages)
                    logger.info(f"[{document_id}] PDF has {num_pages} pages. Dispatching page-chunked parallel prompts to Gemini LLM API...")
                    logs.append(f"[{datetime.utcnow().isoformat()}] Initiating page-chunked parallel extraction ({num_pages} pages).")
                    
                    # 3a. Extract metadata first
                    metadata = await gemini_service.extract_account_metadata(pdf_text)
                    if metadata:
                        meta_metrics = metadata.get("_metrics", {})
                        input_tokens += meta_metrics.get("input_tokens", 0)
                        output_tokens += meta_metrics.get("output_tokens", 0)
                        model_used = meta_metrics.get("model_used", settings.GEMINI_MODEL)
                        
                        # 3b. Group pages into 5-page chunks to respect daily quota limits on Gemini Free Tier
                        chunk_size = 5
                        page_chunks = [pages_text[i:i + chunk_size] for i in range(0, num_pages, chunk_size)]
                        logs.append(f"[{datetime.utcnow().isoformat()}] Extracted account metadata. Processing {len(page_chunks)} page chunks in parallel...")
                        
                        async def process_chunk(chunk_idx: int, pages: list[str]):
                            chunk_str = "\n".join(pages)
                            return await gemini_service.extract_transactions_chunk(chunk_str)

                        tasks = [process_chunk(idx, chunk) for idx, chunk in enumerate(page_chunks)]
                        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        # 3c. Aggregate results
                        aggregated_transactions = []
                        for idx, r in enumerate(chunk_results):
                            if isinstance(r, Exception):
                                logger.error(f"[{document_id}] Chunk {idx + 1} extraction failed: {r}")
                                logs.append(f"[{datetime.utcnow().isoformat()}] Error extracting chunk {idx + 1}: {r}")
                                continue
                            if r:
                                chunk_txs = r.get("transactions") or []
                                aggregated_transactions.extend(chunk_txs)
                                chunk_metrics = r.get("_metrics", {})
                                input_tokens += chunk_metrics.get("input_tokens", 0)
                                output_tokens += chunk_metrics.get("output_tokens", 0)
                                logger.info(f"[{document_id}] Chunk {idx + 1}/{len(page_chunks)} returned {len(chunk_txs)} transactions.")
                        
                        extracted_data = {
                            **metadata,
                            "transactions": aggregated_transactions
                        }
                        logs.append(f"[{datetime.utcnow().isoformat()}] Gemini API successfully extracted structured data via chunking. Total transactions: {len(aggregated_transactions)}.")
                        logger.info(f"[{document_id}] Gemini LLM page-chunked extraction successful. Total transactions: {len(aggregated_transactions)}.")
                        stages.append("detected")
                    else:
                        logs.append(f"[{datetime.utcnow().isoformat()}] Gemini API metadata extraction returned None. Falling back.")

                if not extracted_data:
                    logs.append(f"[{datetime.utcnow().isoformat()}] Gemini API extraction failed or returned empty. Dropping back to heuristic parser.")
                    logger.warning(f"[{document_id}] Gemini extraction empty or failed. Falling back to offline heuristics.")

            if not extracted_data:
                # Fallback to local heuristic regex parser
                logger.info(f"[{document_id}] Executing offline regex heuristic parser...")
                extracted_data = FallbackStatementParser.parse_statement(pdf_text)
                logs.append(f"[{datetime.utcnow().isoformat()}] Offline regex-based parser executed successfully.")
                logger.info(f"[{document_id}] Offline parser complete.")
                stages.append("detected")

            logger.info(f"[{document_id}] Target detected -> Bank: '{extracted_data.get('bank_name')}', Account Holder: '{extracted_data.get('account_holder_name')}'")

            # 4. Save Extracted Data into database inside a single atomic transaction
            logger.info(f"[{document_id}] Writing structured statement documents to PostgreSQL on Neon...")
            async with db_manager.session_factory() as session:
                document_repo = BaseRepository(session, "documents")
                account_repo = BaseRepository(session, "accounts")
                transaction_repo = BaseRepository(session, "transactions")

                # Insert Account info
                account_doc = {
                    "document_id": document_id,
                    "person_id": uuid.UUID(person_id) if isinstance(person_id, str) else person_id,
                    "bank_name": extracted_data.get("bank_name", "Unknown Bank"),
                    "account_holder_name": extracted_data.get("account_holder_name", "Customer"),
                    "account_number": extracted_data.get("account_number", "Unknown"),
                    "account_type": extracted_data.get("account_type", "savings"),
                    "ifsc_code": extracted_data.get("ifsc_code"),
                    "branch": extracted_data.get("branch"),
                    "opening_balance": float(extracted_data.get("opening_balance") or 0.0),
                    "closing_balance": float(extracted_data.get("closing_balance") or 0.0),
                    "statement_period": extracted_data.get("statement_period"),
                    "statement_month": extracted_data.get("statement_month"),
                    "created_at": datetime.utcnow()
                }
                
                account_id = await account_repo.create(account_doc)
                logs.append(f"[{datetime.utcnow().isoformat()}] Persisted Account document. ID: {account_id}.")
                logger.info(f"[{document_id}] Stored Account record. Generated UUID: {account_id}")

                # Insert Transactions
                raw_transactions = extracted_data.get("transactions") or []
                logger.info(f"[{document_id}] Ingesting {len(raw_transactions)} transactions in batch...")
                
                from app.database.models import Merchant, Transaction
                from sqlalchemy import select

                # 1. Pre-extract and clean all unique merchant names
                merchant_names = set()
                for tx in raw_transactions:
                    name = tx.get("merchant_name")
                    if name:
                        merchant_names.add(name.strip())

                # 2. Batch fetch existing merchants matching these names
                merchant_cache = {}
                if merchant_names:
                    stmt = select(Merchant).where(Merchant.name.in_(list(merchant_names)))
                    result = await session.execute(stmt)
                    existing_merchants = result.scalars().all()
                    for m in existing_merchants:
                        merchant_cache[m.name] = m.id

                    # 3. Create missing merchants in a batch
                    new_merchants = []
                    for name in merchant_names:
                        if name not in merchant_cache:
                            new_m = Merchant(
                                id=uuid.uuid4(),
                                name=name,
                                created_at=datetime.utcnow()
                            )
                            session.add(new_m)
                            new_merchants.append(new_m)
                    
                    if new_merchants:
                        await session.flush()
                        for new_m in new_merchants:
                            merchant_cache[new_m.name] = new_m.id

                # 4. Instantiate all Transaction models and add to session
                transaction_instances = []
                for index, tx in enumerate(raw_transactions):
                    norm_tx = StatementNormalizer.normalize_transaction(tx)
                    
                    tx_date = datetime.strptime(norm_tx["transaction_date"], "%Y-%m-%d").date()
                    val_date = datetime.strptime(norm_tx["value_date"], "%Y-%m-%d").date() if norm_tx.get("value_date") else tx_date
                    
                    # Resolve merchant_id from cache
                    merchant_id = None
                    merchant_name = norm_tx.get("merchant_name")
                    if merchant_name:
                        merchant_id = merchant_cache.get(merchant_name.strip())

                    tx_instance = Transaction(
                        id=uuid.uuid4(),
                        document_id=uuid.UUID(document_id) if isinstance(document_id, str) else document_id,
                        account_id=uuid.UUID(account_id) if isinstance(account_id, str) else account_id,
                        merchant_id=merchant_id,
                        transaction_date=tx_date,
                        value_date=val_date,
                        narration=norm_tx["narration"],
                        debit_amount=norm_tx["debit_amount"],
                        credit_amount=norm_tx["credit_amount"],
                        running_balance=norm_tx["running_balance"],
                        reference_number=norm_tx["reference_number"],
                        utr_upi_ref=norm_tx["utr_upi_ref"],
                        cheque_number=norm_tx["cheque_number"],
                        category=norm_tx["category"],
                        classification=norm_tx["classification"],
                        type=norm_tx["type"],
                        created_at=datetime.utcnow()
                    )
                    transaction_instances.append(tx_instance)

                if transaction_instances:
                    session.add_all(transaction_instances)
                    await session.flush()
                    logger.info(f"[{document_id}] Successfully batched-inserted {len(transaction_instances)} transactions.")

                logs.append(f"[{datetime.utcnow().isoformat()}] Stored {len(raw_transactions)} transactions.")
                stages.append("normalized")
                stages.append("stored")

                # Update Document Status to COMPLETED
                await document_repo.update(document_id, {
                    "status": DocumentStatus.COMPLETED,
                    "updated_at": datetime.utcnow()
                })
                
                await session.commit()
                logs.append(f"[{datetime.utcnow().isoformat()}] Statement pipeline completed successfully.")
                logger.info(f"[{document_id}] Transaction committed successfully. Status updated to COMPLETED.")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[{document_id}] Pipeline failure: {error_msg}", exc_info=True)
            logs.append(f"[{datetime.utcnow().isoformat()}] CRITICAL PIPELINE ERROR: {error_msg}")
            
            # Set document status to FAILED in a separate session
            async with db_manager.session_factory() as session:
                try:
                    document_repo = BaseRepository(session, "documents")
                    await document_repo.update(document_id, {
                        "status": DocumentStatus.FAILED,
                        "error_message": error_msg,
                        "updated_at": datetime.utcnow()
                    })
                    await session.commit()
                    logger.info(f"[{document_id}] Failure status committed to db.")
                except Exception as db_ex:
                    logger.error(f"[{document_id}] Failed logging pipeline failure status: {db_ex}")

        finally:
            # Record processing metadata logs
            elapsed = time.time() - start_time
            logger.info(f"[{document_id}] Writing pipeline metrics (took {round(elapsed, 2)}s)...")
            async with db_manager.session_factory() as session:
                try:
                    metadata_repo = BaseRepository(session, "processing_metadata")
                    metadata_doc = {
                        "document_id": document_id,
                        "processing_time_seconds": round(elapsed, 3),
                        "model_used": model_used,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "stages_completed": stages,
                        "logs": "\n".join(logs),
                        "created_at": datetime.utcnow()
                    }
                    await metadata_repo.create(metadata_doc)
                    await session.commit()
                    logger.info(f"[{document_id}] Successfully recorded processing telemetry.")
                except Exception as meta_ex:
                    logger.error(f"[{document_id}] Could not save processing telemetry logs: {meta_ex}")
