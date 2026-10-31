import os
import logging
import io
from typing import Dict, Any
from fastapi import FastAPI, File, UploadFile, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd


# Configuración de Logging Seguro 
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO"). upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("fastapi_csv_service")

app = FastAPI(
    title="CSV Processing Microservice",
    description="A production-grade, secure microservice for CSV cleaning and transformation built with FastAPI and Pandas.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


# Configuración de Logging seguro
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("fastapi_cvs_service")

app = FastAPI(
    title="CSV Processing Microservice",
    description="A production-grade, secure microservice for CSV cleaning and transformation built with FastAPI snd PAndas.",
    version="1.0.0",
    docs_urk="/docs",
    redoc_url="/redoc"
)


#configuración de CORS restrictiva
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINIS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# Limites de seguridad para prevenir DoS
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "5"))
MAX_FILE_SIZE_BITES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_ROWS = int(os.getenv("MAX_ROWS", "10000"))


# Middleware de Cabeceras de Seguridad
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Sistema Global de Gestión de Errores
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(f"HTTP error occurred: {exc.status_code} - {exc.detail} - Path: {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.status_code,
                "message": exc.detail
            }
        }
    )
    
@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """Endpoint de verificación de estado del servicio."""
    return {"status": "healthy", "service": "csv-processing-microservice"}
    
@app.post("/api/v1/process-csv", tags=["CSV Processor"])
async def process_csv_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Procesa, valida y limpia un archivo CSV subido por el usuario.
    Aplica controles estrictos de tamaño, tipo y estructura para prevenir DoS e inyecciones.
    """
    logger.info(f"Recibiendo solicitud de procesamiento para archivo: {file.filename}")
        
    # 1. Validación de extensión del archivo.
    if not file.filename or not file.filename.lower().endswith(".csv"):
        logger.warning(f"Rechazado: Extención de archivo inválida -> {file.filename}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only .csv files are supporte."
        )
        
    # 2. Lectura y validación del tamaño del archivo 
    try:
        contents = await file.read()
        file_size = len(contents)
    except Exception as e:
        logger.error(f"Error al leer el archivo subido: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read the uploaded file."
        )    
        
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty."
        )
        
    if file_size > MAX_FILE_SIZE_BITES:
        logger.warning(f"Rechazadp: Archivo demasiado grande ({file_size} bytes)")
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_TOO_LARGE,
            detail=f"File size exceeds the maximum allowed limit of {MAX_FILE_SIZE_MB}MB."
        )
        
    # 3. Procesamiento seguro con Pandas
    try:
        buffer = io.BytesIO(contents)
        
        # Leer especificando nrows para proteger contra archivos masivos
        df = pd.read_csv(buffer, nrows=MAX_ROWS + 1)
        
        if len(df) > MAX_ROWS:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"CSV contains more than the maximum alloed limit of {MAX_ROWS}rows."     
            )
            
        if df.empty or len(df.columns) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The CSV file is empty or contains no valid columns."
            )
            
        # Normalización de nombres de columnas
        df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]
    
        # Generar resumen analítico para limitar la respuesta de la API
        row_count = len(df)
        column_count = len(df.columns)
        columns_list = list(df.columns)
        
        # Muestra limitada de datos (primeras 5 filas)
        preview_data = df.head(5).fillna("").to_dict(orient="records")
        
        logger.info(f"Archivo procesdo exitosamente: {row_count} filas, {column_count} columnas.")
          
        return {
            "success": True,
            "filename": file.filename,
            "metadata": {
                "total_rows": row_count,
                "total_columns": column_count,
                "columns": columns_list
            },
            "preview": preview_data
        } 
        
    except pd.errors.EmptyDataError:
        logger.warning("El archivo CSV está vacío o corrupto.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The CSV file is empty or malformed."
        )
    except pd.errors.ParserError:
        logger.warning("Error al pasear el archivo CSV (malformado).")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not parse the CSV file due to malformed structure."
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error inesperado procesando el CSV: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the CSV file."
        )
    
    
    