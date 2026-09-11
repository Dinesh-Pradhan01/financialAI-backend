import json
import os
from typing import Type
import google.generativeai as genai
from loguru import logger
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from app.config import settings
from app.services.agreement.exceptions import GeminiExtractionException, ConfigurationException

class GeminiService:
    @staticmethod
    def _initialize_client():
        api_key = os.getenv("GEMINI_API_KEY", settings.GEMINI_API_KEY if hasattr(settings, "GEMINI_API_KEY") else None)
        if not api_key:
            raise ConfigurationException("GEMINI_API_KEY is not configured.")
        genai.configure(api_key=api_key)

    @staticmethod
    def extract_structured_data(text: str, schema_class: Type[BaseModel]) -> dict:
        GeminiService._initialize_client()
        
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
        logger.info(f"Using Gemini model: {model_name} for structured extraction")

        schema_json = schema_class.model_json_schema()

        prompt = f"""
You are an expert contract and agreement data extraction system.
Extract the relevant financial and temporal data from the document text below.

# STRICT RULES
1. Extract ONLY information actually present in the agreement.
2. NEVER hallucinate or infer missing values.
3. Return null for fields that are not found.
4. Preserve monetary values correctly. Distinguish contract value from periodic payments where possible.
5. Identify the primary currency separately (use standard 3-letter codes like USD, EUR, INR if clear).
6. Identify effective/start/commencement dates.
7. Identify expiry/end/termination dates when applicable.
8. Do not include legal commentary or summarize the agreement.
9. You must respond strictly with valid JSON matching the following JSON Schema:

{json.dumps(schema_json, indent=2)}

Document Text:
=============================
{text[:30000]}  # Limiting text to prevent context overload if document is excessively large
=============================
        """

        try:
            # Using standard gemini generation, requesting JSON response format
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config={"response_mime_type": "application/json"}
            )
            response = model.generate_content(prompt)
            
            if not response.text:
                raise GeminiExtractionException("Gemini returned an empty response.")
                
            data = json.loads(response.text)
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Gemini output was not valid JSON: {e}")
            raise GeminiExtractionException("Failed to parse Gemini output as JSON.")
        except Exception as e:
            logger.error(f"Gemini API Exception: {e}")
            raise GeminiExtractionException(f"LLM Extraction failed: {str(e)}")
