from typing import Any, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.logging import logger


class AppException(Exception):
    """Base application exception with machine error code and status code."""

    def __init__(
        self,
        message: str,
        error_code: str = "app_error",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", details: Optional[Any] = None):
        super().__init__(
            message=message,
            error_code="not_found",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ValidationException(AppException):
    def __init__(self, message: str = "Validation failed", details: Optional[Any] = None):
        super().__init__(
            message=message,
            error_code="validation_error",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Register uniform error handlers for all exceptions."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        logger.warning(f"AppException on {request.method} {request.url.path}: [{exc.error_code}] {exc.message}")
        content = {
            "error": exc.error_code,
            "message": exc.message,
        }
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # Format HTTP status into snake_case error code
        status_code = exc.status_code
        if status_code == status.HTTP_404_NOT_FOUND:
            error_code = "not_found"
            message = exc.detail if exc.detail != "Not Found" else "The requested resource was not found."
        elif status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
            error_code = "method_not_allowed"
            message = "HTTP method not allowed for this endpoint."
        # If endpoint raised HTTPException with a structured dict detail, forward it intact
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=status_code, content=exc.detail)

        if status_code == status.HTTP_404_NOT_FOUND:
            error_code = "not_found"
            message = exc.detail if exc.detail != "Not Found" else "The requested resource was not found."
        elif status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
            error_code = "method_not_allowed"
            message = "HTTP method not allowed for this endpoint."
        elif status_code == status.HTTP_401_UNAUTHORIZED:
            error_code = "unauthorized"
            message = str(exc.detail)
        elif status_code == status.HTTP_403_FORBIDDEN:
            error_code = "forbidden"
            message = str(exc.detail)
        else:
            error_code = f"http_{status_code}"
            message = str(exc.detail)

        return JSONResponse(
            status_code=status_code,
            content={
                "error": error_code,
                "message": message,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning(f"Validation error on {request.method} {request.url.path}: {exc.errors()}")
        # Extract a clean, human-readable summary of errors
        first_error = exc.errors()[0] if exc.errors() else None
        if first_error:
            loc = " -> ".join(str(l) for l in first_error.get("loc", []) if l != "body")
            msg = first_error.get("msg", "Invalid parameter")
            readable_msg = f"{loc}: {msg}" if loc else msg
        else:
            readable_msg = "Invalid request payload."

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "validation_error",
                "message": readable_msg,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Never expose raw stack traces to users; log full traceback internally
        logger.exception(f"Unhandled server error processing {request.method} {request.url.path}: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_server_error",
                "message": "An unexpected error occurred. Please contact the administrator.",
            },
        )
