# Usar una imagen oficial de Python ligera
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar el archivo de dependencias e instalarlas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código (main.py)
RUN useradd --create-home --uid 10001 appuser
COPY main.py .
USER appuser

# Exponer el puerto que usará FastAPI
EXPOSE 8000

# Comando para iniciar el servidor cuando arranque el contenedor
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1

    CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]