import json
import logging
import asyncio
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
import google.generativeai as genai
from app.config import settings
from app.ai.prompts import (
    SYSTEM_INSTRUCTION, 
    USER_PROMPT_TEMPLATE, 
    METADATA_PROMPT_TEMPLATE, 
    TRANSACTIONS_PROMPT_TEMPLATE, 
    AI_VIEW_PROMPT_TEMPLATE, 
    DOCUMENT_VERIFICATION_PROMPT_TEMPLATE,
    TARGET_CLASSIFICATION_PROMPT_TEMPLATE,
    RUTHLESS_MA_PROMPT_TEMPLATE,
    BUSINESS_REGISTRATION_PROMPT_TEMPLATE
)

logger = logging.getLogger(__name__)

# Pydantic schemas for structured extraction from Gemini API
class ExtractedBusinessRegistrationSchema(BaseModel):
    company_name: Optional[str]
    business_pan: Optional[str]
    cin: Optional[str]
    gstin: Optional[str]
    date_of_incorporation: Optional[str]
    registered_address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    pincode: Optional[str]
    udyam_number: Optional[str]

class DocumentVerificationSchema(BaseModel):
    is_readable: bool
    quality_score: float
    extracted_id: Optional[str]
    notes: Optional[str]

class ExtractedTransactionSchema(BaseModel):
    transaction_date: str  # YYYY-MM-DD
    value_date: Optional[str]
    narration: str
    debit_amount: float
    credit_amount: float
    running_balance: float
    reference_number: Optional[str]
    utr_upi_ref: Optional[str]
    cheque_number: Optional[str]
    merchant_name: Optional[str]
    classification: str
    category: str

class ExtractedStatementSchema(BaseModel):
    bank_name: str
    account_holder_name: str
    account_number: str
    account_type: str
    ifsc_code: Optional[str]
    branch: Optional[str]
    opening_balance: float
    closing_balance: float
    statement_period: str
    statement_month: str
    transactions: List[ExtractedTransactionSchema]

class ExtractedAccountMetadataSchema(BaseModel):
    bank_name: str
    account_holder_name: str
    account_number: str
    account_type: str
    ifsc_code: Optional[str]
    branch: Optional[str]
    opening_balance: float
    closing_balance: float
    statement_period: str
    statement_month: str

class ExtractedTransactionsChunkSchema(BaseModel):
    transactions: List[ExtractedTransactionSchema]

class TargetClassificationSchema(BaseModel):
    matched_classification_ids: List[int]
    primary_basic_industry: str
    scale_tier: str
    classification_reasoning: str

class PeerValuationSchema(BaseModel):
    company_id: int
    company_name: str
    ticker: str
    market_cap_cr: float
    ttm_revenue_cr: float
    basic_industry: str
    similarity_rank: int
    peer_fit_confidence: Literal["Very High", "High", "Moderate High", "Moderate"] = Field(description="Must be strictly one of these four values.")
    reasoning: str = Field(description="STRICT LIMIT: Maximum 2 sentences and 40 words explaining overlap. Do not exceed.")

class TopCompetitorsResponseSchema(BaseModel):
    target_summary: str
    top_competitors: List[PeerValuationSchema]

class GeminiExtractionService:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(1)
        self.api_key = settings.GEMINI_API_KEY
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(
                    model_name=settings.GEMINI_MODEL,
                    system_instruction=SYSTEM_INSTRUCTION
                )
                logger.info("Gemini AI Extraction Service initialized successfully.")
            except Exception as e:
                logger.error(f"Error configuring Gemini SDK: {e}")
                self.model = None
        else:
            self.model = None
            logger.warning("GEMINI_API_KEY is not set. Gemini Extraction Service will run in offline fallback mode.")

    def is_available(self) -> bool:
        return self.model is not None

    async def _generate_content_with_retry(self, prompt: str, generation_config: Any) -> Any:
        """Call Gemini model with sequential semaphore control and exponential backoff retry for 429 errors."""
        async with self.semaphore:
            # Space requests to prevent hitting the 15 RPM rate limit
            await asyncio.sleep(4.0)
            
            max_retries = 3
            retry_delay = 5.0
            for attempt in range(max_retries):
                try:
                    response = await asyncio.to_thread(
                        self.model.generate_content,
                        prompt,
                        generation_config=generation_config
                    )
                    return response
                except Exception as e:
                    err_str = str(e)
                    if ("429" in err_str or "rate limit" in err_str.lower() or "quota" in err_str.lower()) and attempt < max_retries - 1:
                        logger.warning(f"Gemini API rate limited (429/quota). Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        raise e

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generates an embedding vector for the given text using Gemini.
        Returns a list of floats, or a zero vector if API is unavailable or fails.
        """
        if not self.is_available():
            logger.warning("Gemini API not configured. Cannot generate embedding.")
            return [0.0] * 1536
            
        try:
            result = await asyncio.to_thread(
                genai.embed_content,
                model="models/gemini-embedding-2",
                content=text,
                task_type="retrieval_document",
                output_dimensionality=1536
            )
            return result['embedding']
        except Exception as e:
            logger.warning(f"Embedding generation failed: {e}")
            return [0.0] * 1536

    async def extract_statement_data(self, pdf_text: str) -> Optional[Dict[str, Any]]:
        """
        Calls Gemini to dynamically extract account and transaction information from statement text.
        Returns a dict matching the ExtractedStatementSchema, or None if extraction fails.
        """
        if not self.is_available():
            logger.warning("Gemini API not configured. Cannot perform online extraction.")
            return None

        try:
            prompt = USER_PROMPT_TEMPLATE.format(pdf_text=pdf_text)
            
            # Setup generation configuration with structured output schema
            generation_config = genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=ExtractedStatementSchema,
                temperature=0.1
            )
            
            # Call Gemini with retry buffer
            response = await self._generate_content_with_retry(prompt, generation_config)
            
            if not response.text:
                logger.error("Empty response received from Gemini API.")
                return None
                
            # Parse the structured JSON response
            extracted_data = json.loads(response.text)
            
            # Add token usage metrics if available
            usage = getattr(response, "usage_metadata", None)
            if usage:
                extracted_data["_metrics"] = {
                    "input_tokens": getattr(usage, "prompt_token_count", 0),
                    "output_tokens": getattr(usage, "candidates_token_count", 0),
                    "model_used": settings.GEMINI_MODEL
                }
            else:
                extracted_data["_metrics"] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "model_used": settings.GEMINI_MODEL
                }
                
            return extracted_data
            
        except Exception as e:
            logger.warning(f"Gemini API extraction failed (falling back to offline rules): {e}")
            return None

    async def extract_account_metadata(self, pdf_text: str) -> Optional[Dict[str, Any]]:
        """
        Calls Gemini to extract only account metadata from the statement text.
        Returns a dict matching the ExtractedAccountMetadataSchema, or None if extraction fails.
        """
        if not self.is_available():
            logger.warning("Gemini API not configured. Cannot perform online extraction.")
            return None

        try:
            prompt = METADATA_PROMPT_TEMPLATE.format(pdf_text=pdf_text)
            generation_config = genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=ExtractedAccountMetadataSchema,
                temperature=0.1
            )
            
            response = await self._generate_content_with_retry(prompt, generation_config)
            
            if not response.text:
                logger.error("Empty response received from Gemini API during metadata extraction.")
                return None
                
            extracted_data = json.loads(response.text)
            
            usage = getattr(response, "usage_metadata", None)
            extracted_data["_metrics"] = {
                "input_tokens": getattr(usage, "prompt_token_count", 0) if usage else 0,
                "output_tokens": getattr(usage, "candidates_token_count", 0) if usage else 0,
                "model_used": settings.GEMINI_MODEL
            }
            return extracted_data
            
        except Exception as e:
            logger.warning(f"Gemini API metadata extraction failed: {e}")
            return None

    async def extract_transactions_chunk(self, chunk_text: str) -> Optional[Dict[str, Any]]:
        """
        Calls Gemini to extract only the transaction list from a segment of statement text.
        Returns a dict containing the transactions chunk, or None if extraction fails.
        """
        if not self.is_available():
            logger.warning("Gemini API not configured. Cannot perform online extraction.")
            return None

        try:
            prompt = TRANSACTIONS_PROMPT_TEMPLATE.format(chunk_text=chunk_text)
            generation_config = genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=ExtractedTransactionsChunkSchema,
                temperature=0.1
            )
            
            response = await self._generate_content_with_retry(prompt, generation_config)
            
            if not response.text:
                logger.error("Empty response received from Gemini API during transactions chunk extraction.")
                return None
                
            extracted_data = json.loads(response.text)
            
            usage = getattr(response, "usage_metadata", None)
            extracted_data["_metrics"] = {
                "input_tokens": getattr(usage, "prompt_token_count", 0) if usage else 0,
                "output_tokens": getattr(usage, "candidates_token_count", 0) if usage else 0,
                "model_used": settings.GEMINI_MODEL
            }
            return extracted_data
            
        except Exception as e:
            logger.warning(f"Gemini API transactions chunk extraction failed: {e}")
            return None

    async def generate_company_ai_view(self, company_name: str, business_category: str, business_type: str, industry: str, description: str) -> Optional[str]:
        """
        Calls Gemini to generate a markdown AI View report of a company.
        """
        if not self.is_available():
            logger.warning("Gemini API not configured. Cannot generate AI view.")
            return "# AI View Unavailable\nGemini API is not configured."

        try:
            prompt = AI_VIEW_PROMPT_TEMPLATE.format(
                company_name=company_name,
                business_category=business_category,
                business_type=business_type,
                industry=industry,
                description=description
            )
            
            generation_config = genai.GenerationConfig(
                response_mime_type="text/plain",
                temperature=0.7
            )
            
            response = await self._generate_content_with_retry(prompt, generation_config)
            
            if not response.text:
                return "# AI View Unavailable\nFailed to generate insights."
                
            return response.text
            
        except Exception as e:
            logger.warning(f"Gemini API AI View generation failed: {e}")
            return f"# Error\nCould not generate AI insights: {e}"

    async def extract_business_registration_data(self, document_text: str) -> Optional[Dict[str, Any]]:
        """
        Calls Gemini to extract business details from registration document text.
        Returns a dict matching the ExtractedBusinessRegistrationSchema, or None if extraction fails.
        """
        if not self.is_available():
            logger.warning("Gemini API not configured. Cannot perform online extraction.")
            return None

        try:
            prompt = BUSINESS_REGISTRATION_PROMPT_TEMPLATE.format(document_text=document_text)
            
            generation_config = genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=ExtractedBusinessRegistrationSchema,
                temperature=0.1
            )
            
            response = await self._generate_content_with_retry(prompt, generation_config)
            
            if not response.text:
                logger.error("Empty response received from Gemini API during business registration extraction.")
                return None
                
            extracted_data = json.loads(response.text)
            
            usage = getattr(response, "usage_metadata", None)
            extracted_data["_metrics"] = {
                "input_tokens": getattr(usage, "prompt_token_count", 0) if usage else 0,
                "output_tokens": getattr(usage, "candidates_token_count", 0) if usage else 0,
                "model_used": settings.GEMINI_MODEL
            }
            return extracted_data
            
        except Exception as e:
            logger.warning(f"Gemini API business registration extraction failed: {e}")
            return None

    async def verify_document_quality(self, document_text: str, document_type: str, expected_id: str) -> Optional[Dict[str, Any]]:
        """
        Calls Gemini to perform a quality check and verification on the document text.
        Returns a dict matching DocumentVerificationSchema, or None if extraction fails.
        """
        if not self.is_available():
            logger.warning("Gemini API not configured. Cannot perform online document verification.")
            return None

        try:
            prompt = DOCUMENT_VERIFICATION_PROMPT_TEMPLATE.format(
                document_type=document_type,
                expected_id=expected_id or "N/A",
                document_text=document_text
            )
            
            generation_config = genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=DocumentVerificationSchema,
                temperature=0.1
            )
            
            response = await self._generate_content_with_retry(prompt, generation_config)
            
            if not response.text:
                logger.error("Empty response received from Gemini API during document verification.")
                return None
                
            extracted_data = json.loads(response.text)
            
            usage = getattr(response, "usage_metadata", None)
            extracted_data["_metrics"] = {
                "input_tokens": getattr(usage, "prompt_token_count", 0) if usage else 0,
                "output_tokens": getattr(usage, "candidates_token_count", 0) if usage else 0,
                "model_used": settings.GEMINI_MODEL
            }
            return extracted_data
            
        except Exception as e:
            logger.warning(f"Gemini API document verification failed: {e}")
            return None

    async def get_target_classification_ids(self, company_name: str, business_category: str, primary_product_service: str, description: str, employees: str, taxonomy_rows: str) -> Optional[Dict[str, Any]]:
        """
        Calls Gemini to classify the unlisted MSME against the exact database taxonomy.
        """
        if not self.is_available():
            logger.warning("Gemini API not configured. Cannot find target classification.")
            return None

        try:
            prompt = TARGET_CLASSIFICATION_PROMPT_TEMPLATE.format(
                company_name=company_name or "Unknown",
                business_category=business_category or "Unknown",
                primary_product_service=primary_product_service or "Unknown",
                description=description or "Unknown",
                employees=employees or "Unknown",
                taxonomy_rows=taxonomy_rows or "No taxonomy provided"
            )
            
            generation_config = genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=TargetClassificationSchema,
                temperature=0.4
            )
            
            response = await self._generate_content_with_retry(prompt, generation_config)
            print("RAW LLM OUTPUT:", response.text)  #log for debugging

            if not response.text:
                logger.error("Empty response received from Gemini API during classification search.")
                return None
                
            # Robust JSON parsing
            text_resp = response.text.strip()
            if text_resp.startswith("```"):
                # Remove markdown code block markers
                import re
                text_resp = re.sub(r'^```(?:json)?\s*', '', text_resp)
                text_resp = re.sub(r'\s*```$', '', text_resp)
            
            # Remove trailing commas that break strict JSON
            import re
            text_resp = re.sub(r',\s*([\]}])', r'\1', text_resp)
            
            extracted_data = json.loads(text_resp)
            return extracted_data
            
        except Exception as e:
            logger.warning(f"Gemini API target classification search failed: {e}")
            return None

    async def get_top_competitors_from_peers(self, company_name: str, business_category: str, primary_product_service: str, business_description: str, employees: str, scale_tier: str, json_list_of_database_peers: str) -> Optional[Dict[str, Any]]:
        """
        Calls Gemini using the Ruthless M&A Analyst prompt to filter and rank a JSON array of peers down to the top 5 matches based on scale.
        """
        if not self.is_available():
            logger.warning("Gemini API not configured. Cannot rank competitors.")
            return None
            
        try:
            prompt = RUTHLESS_MA_PROMPT_TEMPLATE.format(
                company_name=company_name or "Unknown Company",
                business_category=business_category or "Unknown",
                primary_product_service=primary_product_service or "Unknown",
                business_description=business_description or "Unknown",
                employees=employees or "Unknown",
                scale_tier=scale_tier or "Unknown",
                json_list_of_database_peers=json_list_of_database_peers
            )
            
            generation_config = genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=TopCompetitorsResponseSchema,
                temperature=0.4
            )
            
            response = await self._generate_content_with_retry(prompt, generation_config)
            print("RAW M&A LLM OUTPUT:", response.text)
            
            if not response.text:
                logger.error("Empty response from Gemini API during M&A competitor ranking.")
                return None
                
            # Robust JSON parsing
            text_resp = response.text.strip()
            if text_resp.startswith("```"):
                # Remove markdown code block markers
                import re
                text_resp = re.sub(r'^```(?:json)?\s*', '', text_resp)
                text_resp = re.sub(r'\s*```$', '', text_resp)
            
            # Remove trailing commas that break strict JSON
            import re
            text_resp = re.sub(r',\s*([\]}])', r'\1', text_resp)
                
            extracted_data = json.loads(text_resp)
            return extracted_data

            
        except Exception as e:
            logger.warning(f"Gemini API M&A competitor ranking failed: {e}")
            return None

gemini_service = GeminiExtractionService()
