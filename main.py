from fastapi import FastAPI, UploadFile, File
import pandas as pd
import io

app = FastAPI(title="Data Cleaning API")

@app.post("/clean")
async def clean_data(file: UploadFile =  File(...)):
    # 1. Leer el srchivo subido en memoria
    contents = await file.read()
    
    #2. Cargar los datos en un DataFrame de Pandas
    df= pd.read_csv(io.BytesIO(contents))
    
    #3. Limpieza de datos básica:
    # Quitar espacios en blanco sobrantes de los nombres de las columnas
    df.columns = df.columns.str.strip()
    
    # Rellenar celdas vacías (NaN) con un texto por defecto para no romper el JSON
    df.fillna("Dato no disponible", inplace=True)
    
    # 4. Convertir la tabla limpia a un formato JSON estructurado
    cleaned_data = df.to_dict(orient="records")
    
    return {
        "filename": file.filename,
        "message": "Datos limpiados y estructurados con éxito",
        "data": cleaned_data
    }