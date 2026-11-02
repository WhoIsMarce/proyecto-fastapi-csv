from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)
URL = "/api/v1/process-csv"
SAMPLE = Path(__file__).parent / "datos_sucios.csv"


def upload(name, content, content_type="text/csv", **params):
    return client.post(URL, files={"file": (name, content, content_type)}, params=params)


def assert_error(response, status, fragment):
    assert response.status_code == status
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == status
    assert fragment in body["error"]["message"]
    

# --- happy path ---------------------


def test_health_check():
    """Verifica que el endpoint de salud corresponda correctamente."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "csv-cleaning-service"}

def test_sample_file_is_cleaned():
    response = upload("datos_sucios.csv", SAMPLE.read_bytes())
    assert response.status_code == 200
    data = response.json()
    assert data["columns"] == ["id", "nombre", "email", "edad", "ciudad"]
    assert data["cleaning"]["column_types"]["edad"] == "integer"
    assert data["cleaning"]["null_counts"]["email"] == 1
    first, second, third, _ = data["preview"]
    assert first["nombre"] == "Pepito Pérez"        # leading space trimmed
    assert first["edad"] == 45                     # text converted to a number
    assert second["email"] is None                  # blank cell becomes null
    assert third["edad"] is None and third["ciudad"] is None
    
    
def test_headers_are_normalized():
    response = upload("a.csv", "First Name, AGE\nAna,30\n")
    assert response.json()["columns"] == ["first_name", "age"]
    
    
def test_empty_rows_and_duplicates_are_dropped():
    response = upload("a.csv", "a,b\n1,x\n,\n1,x\n2,y\n")
    report = response.json()["cleaning"]
    assert report["rows_in"] == 4
    assert report["rows_out"] == 2
    assert report["empty_rows_dropped"] == 1
    assert report["duplicate_rows_dropped"] == 1
    
    
def test_preview_rows_parameter():
    rows = "\n".join(f"{i},v{i}" for i in range(20))
    response = upload("a.csv", "n,v\n" + rows, preview_rows=3)
    assert len(response.json()["preview"]) == 3
    
    
def test_semicolon_delimiter_is_detected():
    response = upload("a.csv", "nombre;edad\nAna;30\n")
    assert response.json()["columns"] == ["nombre", "edad"]
    
    
def test_latin1_file_is_detected():
    content = "nombre.ciudad\nPepito, Medellín\n".encode("latin-1")
    data = upload("a.csv", content).json()
    assert data["encoding"].startswith("latin-1")
    assert data["preview"][0]["ciudad"] == "Medellín"
    
    
def test_infinity_and_nan_strings_stay_text():
    response = upload("a.csv", "v\ninf\n1\n")
    assert response.status_code == 200
    assert response.json()["cleaning"]["column_types"]["v"] == "text"
    
    
    
#--- rejections ------------------------------------------
def test_rejects_wrong_extension():
    assert_error(upload("notes.txt", "hello", "text/plain"), 400, "Invalid file format")


def test_rejects_empty_file():
    assert_error(upload("empty.csv", ""), 400, "empty")
    
    
def test_rejects_binary_file_renamed_to_csv():
    assert_error(upload("x.csv", b"MZ\x90\x00\x03\x00\x00\x00"), 400, "binary")
    
    
def test_rejects_header_only_csv():
    assert_error(upload("h.csv", "a,b,c\n"), 400, "no data rows")
    
    
def test_rejects_too_many_rows(monkeypatch):
    monkeypatch.setattr("main.MAX_ROWS", 3)
    assert_error(upload("r.csv", "a\n1\n2\n3\n4\n"), 413, "rows")
    
    
def test_rejects_oversized_file_in_handler(monkeypatch):
    monkeypatch.setattr(main, "MAX_FILE_SIZE_BYTES", 100)
    assert_error(upload("big.csv", "a\n" + "1\n" * 500), 413, "limit")
    
    
def test_rejects_oversized_request_in_middleware(monkeypatch):
    monkeypatch.setattr(main, "MAX_FILE_SIZE_BYTES", 100)
    big = "a\n" + "1\n" * 40_000   # well past limit + multipart overhead
    assert_error(upload("big.csv", big), 413, "limit")
    
    
    
# --- error format ------------------------------------------
def test_unknown_route_uses_json_error_format():
    assert_error(client.get("/nope"), 404, "Not Found")
    
    
def test_missing_file_uses_json_error_format():
    response = client.post(URL)
    assert_error(response, 422, "file")
    
    
    
# --- security ---------------------------------------------
def test_security_headers_present():
    headers = client.get("/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" in headers
    
    
def test_cors_is_closed_by_default():
    response = client.options(
        "/health",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers
    
    
