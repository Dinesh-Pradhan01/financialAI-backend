from typing import Any, Dict, Optional
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

def success_response(message: str = "Success", data: Optional[Any] = None, status_code: int = 200) -> JSONResponse:
    content = {
        "success": True,
        "message": message,
    }
    if data is not None:
        content["data"] = jsonable_encoder(data)
    return JSONResponse(status_code=status_code, content=content)

def error_response(message: str = "An error occurred", errors: Optional[list] = None, status_code: int = 400) -> JSONResponse:
    content = {
        "success": False,
        "message": message,
    }
    if errors is not None:
        content["errors"] = errors
    return JSONResponse(status_code=status_code, content=content)
