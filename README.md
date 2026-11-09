# CSV Cleaning Service

[![CI](https://github.com/WhoIsMarce/proyecto-fastapi-csv/actions/workflows/ci.yml/badge.svg)](https://github.com/WhoIsMarce/proyecto-fastapi-csv/actions/workflows/ci.yml)

A small HTTP service that takes a messy CSV file and returns clean, typed JSON. Built with FastAPI and pandas, packaged with Docker.

You upload a file; the service trims whitespace, turns blank cells into real `null`s, drops empty and duplicate rows, detects numeric columns, and sends back a preview of the result along with a short report of what it changed. It does not store anything: each request is processed in memory and forgotten.

## Quick start

### With Docker

```bash
git clone https://github.com/WhoIsMarce/proyecto-fastapi-csv.git
cd proyecto-fastapi-csv
docker build -t csv-cleaner .
docker run -d -p 8000:8000 --name csv-cleaner csv-cleaner
```

Check that it is up:

```bash
curl http://localhost:8000/health
```

To stop and remove it: `docker rm -f csv-cleaner`.

### Without Docker

Requires Python 3.12 or newer.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## Starting it again later

Closing the terminal does not undo anything you installed. What you need to repeat depends on how you run it.

**Docker.** The container survives closing the terminal, because `-d` runs it in the background. Docker Desktop has to be open. If the container was stopped (after a reboot, for example):

```bash
docker start csv-cleaner
```

If it has been removed, run the `docker run` command from above again. The image is already built, so there is no need to rebuild it.

**Without Docker.** Only the virtual environment needs reactivating. The packages are still installed in it:

```bash
cd proyecto-fastapi-csv
source .venv/bin/activate        # Git Bash on Windows: source .venv/Scripts/activate
uvicorn main:app --reload
```

## Using the API

Interactive docs are served at `http://localhost:8000/docs`. The same thing from the command line, using the sample file in this repo:

```bash
curl -F "file=@datos_sucios.csv;type=text/csv" \
     "http://localhost:8000/api/v1/process-csv?preview_rows=3"
```

### `POST /api/v1/process-csv`

| Part | Description |
| --- | --- |
| `file` (multipart form field) | The CSV file. Must have a `.csv` extension. |
| `preview_rows` (query, optional) | How many cleaned rows to return. Default 5, range 1 to 100. |

Response for the sample file (`preview_rows=3`). The sample has 7 data rows with extra spaces, blank cells, one fully empty row and one exact duplicate, so every cleaning rule shows up in the report:

```json
{
  "success": true,
  "filename": "datos_sucios.csv",
  "encoding": "utf-8",
  "columns": ["id", "nombre_completo", "email", "edad", "ciudad"],
  "cleaning": {
    "rows_in": 7,
    "rows_out": 5,
    "empty_rows_dropped": 1,
    "duplicate_rows_dropped": 1,
    "null_counts": {"id": 0, "nombre_completo": 0, "email": 1, "edad": 1, "ciudad": 1},
    "column_types": {"id": "integer", "nombre_completo": "text", "email": "text", "edad": "integer", "ciudad": "text"}
  },
  "preview": [
    {"id": 1, "nombre_completo": "Juan Perez", "email": "juan@email.com", "edad": 28, "ciudad": "Madrid"},
    {"id": 2, "nombre_completo": "Ana Gomez", "email": null, "edad": 35, "ciudad": "Buenos Aires"},
    {"id": 3, "nombre_completo": "Luis Alberto", "email": "luis@email.com", "edad": null, "ciudad": null}
  ]
}
```

### `GET /health`

Returns `{"status": "healthy", "service": "csv-cleaning-service"}`. The Docker image uses it for its health check.

### Errors

Every error, including 404s and validation failures, has the same shape:

```json
{"success": false, "error": {"code": 400, "message": "Invalid file format. Only .csv files are supported."}}
```

| Status | When |
| --- | --- |
| 400 | Wrong extension, empty file, binary content, header with no data rows, malformed CSV |
| 413 | File larger than `MAX_FILE_SIZE_MB`, or more than `MAX_ROWS` rows |
| 422 | Missing `file` field or an invalid query parameter |
| 500 | Anything unexpected. Details go to the log, never to the client |

## What "cleaning" means here

Applied in this order:

1. **Headers** are lowercased, trimmed, and spaces become underscores (`First Name` becomes `first_name`). Names that collide get a numeric suffix.
2. **Delimiter** is detected from `,`, `;`, tab or `|`, so files exported by spreadsheets in other locales work.
3. **Encoding**: UTF-8 first (with or without BOM), then latin-1 as a fallback. The one used is reported in `encoding`.
4. **Whitespace** is trimmed from every cell, and cells that end up blank become `null`.
5. **Rows** that are entirely empty are dropped, then exact duplicates are dropped.
6. **Types**: a column becomes `integer` or `float` only if every non-empty value in it is numeric. Otherwise it stays `text`. Dates are not parsed.

Everything is counted in the `cleaning` section of the response, so you can see what was removed.

## Configuration

All settings are environment variables. Pass them with `docker run -e NAME=value`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MAX_FILE_SIZE_MB` | `5` | Largest accepted upload |
| `MAX_ROWS` | `10000` | Largest accepted number of data rows |
| `ALLOWED_ORIGINS` | empty | Comma-separated list of origins allowed by CORS. Empty means no cross-origin access |
| `ENABLE_DOCS` | `true` | Set to `false` to turn off `/docs`, `/redoc` and `/openapi.json` |
| `LOG_LEVEL` | `INFO` | Standard Python logging level |

Example:

```bash
docker run -d -p 8000:8000 \
  -e MAX_FILE_SIZE_MB=10 \
  -e ALLOWED_ORIGINS=https://app.example.com \
  -e ENABLE_DOCS=false \
  csv-cleaner
```

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

The tests cover the cleaning rules, the size and row limits, encodings, error formats and the security headers.

```text
main.py                 the whole service
test_main.py            test suite
datos_sucios.csv        sample input
requirements.txt        runtime dependencies (pinned)
requirements-dev.txt    adds pytest and httpx
Dockerfile              python:3.12-slim, runs as a non-root user
```

## Limits and things to know

- **No authentication and no rate limiting.** If you expose this beyond your machine, put it behind a reverse proxy or API gateway that provides both.
- **Size limits are enforced inside the app,** which means the upload has already been received when the check runs. A proxy such as nginx (`client_max_body_size`) is the right place for a hard cap on a public deployment.
- **Each request holds its file in memory.** With the defaults that is at most 5 MB plus the DataFrame, but many parallel uploads add up. Size the container accordingly.
- **Cell values are returned as they are.** A text value starting with `=`, `+`, `-` or `@` is not altered. If you feed this JSON into a spreadsheet export, escape those cells there.
- **HSTS header** is sent on every response but only has an effect when the service is served over HTTPS, which you need to arrange in front of it.
- Only the first 5 to 100 rows are returned in the preview. The service reports on the whole file but does not return all of it.

---

[Article: What My FastAPI CSV Upload Service Got Wrong: Four Bugs the Test Suite Never Caught](https://dev.to/whoismarce/what-my-fastapi-csv-upload-service-got-wrong-four-bugs-the-test-suite-never-caught-l1k)
Developed by [Marcela Zapata Vanegas](https://www.linkedin.com/in/marcelazapatavanegas/), technical writer and full stack developer.
