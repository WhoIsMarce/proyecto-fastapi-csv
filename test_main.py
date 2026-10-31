import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_check():
    """Verifica que el endpoint de salud corresponda correctamente."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "csv-processing-microservice"
  
def test_process_valid_csv(): 
    """Verifica el procesamiento exitoso de un archivo CSV válido."""
    csv_content = "nombre, edad, ciudad\nAna,30,Madrid\nCarlos,25,Buenos Aires"
    files = {"file": ("datos.csv", csv_content, "text/csv")}
    
    response = client.post("/api/v1/process-csv", files=files)
    assert response.status_code == 200
    data = response.json()
    
    assert data ["success"] is True
    assert data ["filename"] == "datos.csv"
    assert data ["metadata"]["total_rows"] == 2
    assert data ["metadata"]["total_columns"] == 3
    assert "nombre" in data["metadata"]["columns"]
    
def test_process_invalid_extension():
    """Verifica que se rechacen archivos que no sean .csv."""
    text_content = "contenido de prueba"
    files = {"file": ("documento.txt", text_content, "text/plain")}
    
    response = client.post("/api/v1/process-csv", files=files)
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "Invalid file format" in data["error"]["message"]
    
def test_process_empty_file():
    """Verifica que se rechacen archivos vacíos."""
    files = {"file": ("vacio.csv", "", "text/csv")}
    
    response = client.post("/api/v1/process-csv", files=files)
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "empty" in data["error"]["message"]
    
def test_security_headers_present():
    """Verifica que las cabeceras de seguridad HTTP se inyecten correctamente."""
    response = client.get("/health")
    assert "x-content-type-options" in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "x-frame-options" in response.headers
    assert response.headers["x-frame-options"] == "DENY"
    
    