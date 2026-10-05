from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
import pypdf
import io
from app.document_classifier.schemas import DocumentClassificationResult
from app.document_classifier.service import DocumentClassificationService

router = APIRouter(
    prefix="/api/documents",
    tags=["Document Classifier"]
)

@router.post("/classify")
async def classify_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        content = await file.read()
        pdf_reader = pypdf.PdfReader(io.BytesIO(content))
        
        num_pages = len(pdf_reader.pages)
        if num_pages == 0:
            raise HTTPException(status_code=400, detail="Empty PDF file")
            
        extracted_text = ""
        
        # Extract from first page
        extracted_text += pdf_reader.pages[0].extract_text() or ""
        
        # Extract from last 2 pages
        if num_pages > 1:
            start_idx = max(1, num_pages - 2)
            for i in range(start_idx, num_pages):
                extracted_text += "\n" + (pdf_reader.pages[i].extract_text() or "")
                
        # Run classification and dispatch
        result = DocumentClassificationService.classify_and_dispatch(
            extracted_text=extracted_text,
            file_bytes=content,
            filename=file.filename,
            background_tasks=background_tasks
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")
