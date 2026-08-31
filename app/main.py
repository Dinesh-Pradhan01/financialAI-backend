from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from app.core.config import settings
from app.core.logging import setup_logging
from app.api import health
from app.middleware.exceptions import ExceptionHandlingMiddleware
# Set up centralized loguru logging
setup_logging()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    version=settings.VERSION,
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation Error: {exc.errors()}")
    logger.info(f"Invalid Payload: {exc.body}")
    return JSONResponse(
        status_code=422,
        content={"message": "Validation Error", "details": exc.errors()}
    )

# Exception Handling Middleware
app.add_middleware(ExceptionHandlingMiddleware)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For production, configure this via settings
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.employee.routes import router as employee_router
from app.api.vendor.routes import router as vendor_router
from app.api.dashboard.routes import router as dashboard_router
from app.api.chatbot.routes import router as chatbot_router

# Include Routers
app.include_router(health.router, tags=["Health Check"])
app.include_router(employee_router, prefix=f"{settings.API_V1_STR}/employees", tags=["Employee"])
app.include_router(vendor_router, prefix=f"{settings.API_V1_STR}/vendors", tags=["Vendor"])
app.include_router(dashboard_router, prefix=f"{settings.API_V1_STR}/dashboard", tags=["Dashboard"])
app.include_router(chatbot_router, prefix=f"{settings.API_V1_STR}/chatbot", tags=["Chatbot"])
