"""CSV cleaning service.

Upload a CSV file, get back cleaned and typed JSON plus a short report of
what was changed.
"""
import csv
import io
import logging
import os
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# ---------------------------------------------------------------------------
# Configuration (all values can be overridden with environment variables)
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "5"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_ROWS = int(os.getenv("MAX_ROWS", "10000"))
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
]
ENABLE_DOCS = os.getenv("ENABLE_DOCS", "true").lower() == "true"

# Multipart framing adds a bit on top of the file itself.
MULTIPART_OVERHEAD_BYTES = 64 * 1024
# Integers beyond 2**53 lose precision in JSON consumers, so they stay as text.
MAX_SAFE_INT = 2**53

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
)
logger = logging.getLogger("csv_service")

app = FastAPI(
    title="CSV Cleaning Service",
    description="Upload a messy CSV, get cleaned and typed JSON back.",
    version="1.1.0",
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


# ---------------------------------------------------------------------------
# Errors: every failure uses the same JSON shape
# ---------------------------------------------------------------------------
def error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": {"code": status_code, "message": message}},
    )


class ClientError(Exception):
    """A problem with the uploaded data, reported back with a 4xx status."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@app.exception_handler(ClientError)
async def client_error_handler(request: Request, exc: ClientError):
    logger.warning("Rejected request to %s: %s", request.url.path, exc.message)
    return error_response(exc.status_code, exc.message)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    return error_response(exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0]
    where = ".".join(str(part) for part in first["loc"])
    return error_response(422, f"Invalid request ({where}): {first['msg']}")


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s", request.url.path, exc_info=exc)
    return error_response(500, "Internal server error.")


# ---------------------------------------------------------------------------
# Middleware: reject oversized bodies early, add security headers
# ---------------------------------------------------------------------------
@app.middleware("http")
async def guard_and_harden(request: Request, call_next):
    response = None
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > MAX_FILE_SIZE_BYTES + MULTIPART_OVERHEAD_BYTES:
                response = error_response(
                    413, f"Request body exceeds the {MAX_FILE_SIZE_MB} MB limit."
                )
        except ValueError:
            response = error_response(400, "Invalid Content-Length header.")

    if response is None:
        response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------
def decode_bytes(raw: bytes) -> tuple[str, str]:
    """Decode uploaded bytes. Tries UTF-8 first, then falls back to latin-1."""
    if b"\x00" in raw:
        raise ClientError(400, "The file looks binary, not like a text CSV.")
    try:
        return raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("latin-1"), "latin-1 (fallback)"


def detect_delimiter(text: str) -> str:
    """Guess the delimiter. Spreadsheets in many locales export with ';'."""
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def normalize_columns(columns) -> list[str]:
    """lower_snake_case headers, with a numeric suffix on collisions."""
    seen: dict[str, int] = {}
    result = []
    for col in columns:
        name = str(col).strip().lower().replace(" ", "_") or "column"
        count = seen.get(name, 0)
        seen[name] = count + 1
        result.append(name if count == 0 else f"{name}_{count}")
    return result


def infer_numeric(series: pd.Series) -> pd.Series | None:
    """Return a numeric version of the column, or None if it is not numeric."""
    present = series.notna()
    if not present.any():
        return None
    numbers = pd.to_numeric(series, errors="coerce")
    if not numbers[present].notna().all():
        return None
    values = numbers.dropna().to_numpy(dtype=float)
    if not np.isfinite(values).all():
        return None
    if (values % 1 == 0).all() and (np.abs(values) < MAX_SAFE_INT).all():
        return numbers.astype("Int64")
    return numbers.astype("float64")


def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows_in = len(df)

    # Trim whitespace and turn blanks into real nulls.
    df = df.apply(lambda col: col.str.strip())
    df = df.mask(df == "", np.nan)

    before = len(df)
    df = df.dropna(how="all")
    empty_rows_dropped = before - len(df)

    before = len(df)
    df = df.drop_duplicates()
    duplicate_rows_dropped = before - len(df)

    for col in df.columns:
        numeric = infer_numeric(df[col])
        if numeric is not None:
            df[col] = numeric

    report = {
        "rows_in": rows_in,
        "rows_out": len(df),
        "empty_rows_dropped": empty_rows_dropped,
        "duplicate_rows_dropped": duplicate_rows_dropped,
        "null_counts": {c: int(df[c].isna().sum()) for c in df.columns},
        "column_types": {
            c: ("integer" if str(df[c].dtype) == "Int64"
                else "float" if str(df[c].dtype) == "float64"
                else "text")
            for c in df.columns
        },
    }
    return df, report


def to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame rows as plain Python values, with nulls as None."""
    as_objects = df.astype(object)
    return as_objects.where(df.notna(), None).to_dict(orient="records")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "csv-cleaning-service"}


# Plain `def` on purpose: FastAPI runs it in a worker thread, so the CPU-bound
# pandas work does not block the event loop.
@app.post("/api/v1/process-csv", tags=["CSV"])
def process_csv_file(
    file: UploadFile = File(...),
    preview_rows: int = Query(5, ge=1, le=100, description="Rows to include in the preview."),
) -> dict[str, Any]:
    filename = os.path.basename(file.filename or "")
    logger.info("Processing upload: %r", filename)

    if not filename.lower().endswith(".csv"):
        raise ClientError(400, "Invalid file format. Only .csv files are supported.")

    # Read at most limit + 1 bytes so an oversized file is detected without
    # loading the whole thing.
    raw = file.file.read(MAX_FILE_SIZE_BYTES + 1)
    if not raw:
        raise ClientError(400, "The uploaded file is empty.")
    if len(raw) > MAX_FILE_SIZE_BYTES:
        raise ClientError(413, f"File exceeds the {MAX_FILE_SIZE_MB} MB limit.")

    text, encoding = decode_bytes(raw)

    try:
        df = pd.read_csv(
            io.StringIO(text),
            sep=detect_delimiter(text),
            dtype=str,
            keep_default_na=False,
            skipinitialspace=True,
            nrows=MAX_ROWS + 1,
        )
    except pd.errors.EmptyDataError:
        raise ClientError(400, "The CSV file is empty.")
    except pd.errors.ParserError:
        raise ClientError(400, "Could not parse the file: the CSV structure is malformed.")

    if len(df) > MAX_ROWS:
        raise ClientError(413, f"CSV has more than the allowed {MAX_ROWS} rows.")
    if df.empty or len(df.columns) == 0:
        raise ClientError(400, "The CSV has a header but no data rows.")

    df.columns = normalize_columns(df.columns)
    df, report = clean_dataframe(df)

    logger.info("Done: %d rows in, %d rows out", report["rows_in"], report["rows_out"])
    return {
        "success": True,
        "filename": filename,
        "encoding": encoding,
        "columns": list(df.columns),
        "cleaning": report,
        "preview": to_records(df.head(preview_rows)),
    }