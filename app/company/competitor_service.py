import os
import json
import asyncio
import re
import logging
from groq import AsyncGroq
from app.config import settings
from google import genai
from datetime import datetime
from google.genai import types

logger = logging.getLogger(__name__)

async def competitors(company_name: str, location: str, industry_type: str, industry_category: str) -> dict:
    """
    Asynchronously identifies market competitors using Groq's web-search enabled LLM.
    """
    
    GQclient = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY") or settings.GROQ_API_KEY)
    GNclient = genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or settings.GEMINI_API_KEY)

    system_prompt = (
        "You are an expert competitive intelligence analyst."
        "Use your web search capabilities to find 3 to 5 direct competitors for the target company based on market overlap. "
        "Output format: valid py.Dict obj in format:"
        "{\"company name\": \"string\", \"location\": \"string\", \"services\": \"string\", \"overlap summary\": \"string\"}"
    )

    user_prompt = (
        f"Find competitors for the following company:\n"
        f"Name: {company_name}\n"
        f"Location: {location}\n"
        f"Industry Type: {industry_type}"
        f"Industry Category: {industry_category}"
        f"Date today(DD-MM-YYYYY): {datetime.now().strftime("%d-%m-%Y")}"
    )

    try:
        response = await GNclient.aio.models.generate_content(
            model="gemini-2.5-flash", 
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                # Enable Google Search natively
                tools=[types.Tool(google_search=types.GoogleSearch())],
                # Gemini safely supports enforcing JSON mode alongside tools
                #response_mime_type="application/json",
                temperature=0.2
            )
            )
        raw_content = response.text
        
            # Clean up markdown code blocks if the model ignores the prompt instruction
        clean_content = re.sub(r"^```(?:json|python)?\s*|\s*```$", "", raw_content.strip(), flags=re.IGNORECASE)
        
        return {"type": "structured","content": json.loads(clean_content)}

    except json.JSONDecodeError as e:
        logger.warning(f"Competitors-API: Failed to parse JSON. Raw output was sent!")
        return {"type": "unstructured","content": raw_content}
    except Exception as e:
        logger.info(f"Error fetching competitors via Gemini: {e}\n"
                    "Trying via Groq Model...!")
        
        try:
            response = await GQclient.chat.completions.create(
                # Using a tool-capable model
                model="openai/gpt-oss-120b", 
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                # Tool calling remains active
                tools=[{"type": "browser_search"}],
                # REMOVED: response_format={"type": "json_object"} to resolve the 400 error
                temperature=0.2
            )
            
            raw_content = response.choices[0].message.content
            
            # Clean up markdown code blocks if the model ignores the prompt instruction
            clean_content = re.sub(r"^```(?:json|python)?\s*|\s*```$", "", raw_content.strip(), flags=re.IGNORECASE)
            
            return {"type": "structured","content": json.loads(clean_content)}
            
        except json.JSONDecodeError as e2:
            logger.warning(f"Competitors-API: Failed to parse JSON. Raw output was sent!")
            return {"type": "unstructured","content": raw_content}
        except Exception as e2:
            logger.error(f"Error fetching competitors via Gemini: {e2}")
            return {"type": "Null","Groq-error": e2,"Gemini-error": e}

 