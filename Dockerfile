# Usar una imagen oficial de Python ligera
FROM python:3.10-slim

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar el archivo de dependencias e instalarlas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código (main.py)
COPY . .

# Exponer el puerto que usará FastAPI
EXPOSE 8000

# Comando para iniciar el servidor cuando arranque el contenedor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]