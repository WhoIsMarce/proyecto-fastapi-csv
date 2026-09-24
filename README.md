# Data Cleaning Microservice: FastAPI + Pandas + Docker

A high-performance, containerized Python microservice designed to ingest messy CSV files, clean the data using Pandas, and return a structured JSON response.

This project demonstrates how to build and containerize a modern, asynchronous API capable of handling data transformation pipelines.

## Architecture

* **FastAPI**: A modern, fast (high-performance) web framework for building APIs with Python, built on standard Python type hints.
* **Pandas**: The industry-standard Python library for data manipulation and analysis, used here to handle missing values and normalize dataset headers.
* **Docker**: Containerizes the microservice (using a lightweight `python:3.10-slim` image) to ensure environment consistency and easy deployment on any cloud provider (e.g., Civo, AWS, DigitalOcean).

## Prerequisites

Before you begin, ensure you have the following installed on your local machine:

* [Docker Desktop](https://www.docker.com/products/docker-desktop/)
* Git

## ⚙️ Setup & Deployment

1. **Clone the repository:**

   ```bash
   git clone https://github.com/whoismarce/proyecto-fastapi-csv.git
   cd proyecto-fastapi-csv
   ```

2. **Build the Docker Image:**
   Execute the following command to build the container image. This will download the Python base image and install the required dependencies (`fastapi`, `pandas`, `uvicorn`, etc.).

   ```bash
   docker build -t fastapi-limpiador .
   ```

3. **Run the Container:**
   Spin up the microservice in detached mode on port 8000:

   ```bash
   docker run -d -p 8000:8000 --name api_python fastapi-limpiador
   ```

## Testing via Swagger UI

One of the greatest features of FastAPI is its auto-generated, interactive API documentation. You don't need external tools like Postman to test this service.

1. Open your web browser and navigate to: `http://localhost:8000/docs`
2. You will see the **Swagger UI** dashboard. Click on the green `POST /clean` endpoint.
3. Click the **"Try it out"** button on the right side.
4. Click **"Choose File"** and upload the `datos_sucios.csv` sample file provided in this repository.
5. Click **"Execute"**.
6. Scroll down to the **"Server response"** section to see the data seamlessly transformed from a messy CSV into clean, structured JSON.

## Teardown

To stop the microservice and remove the container from your environment to free up resources, run the following commands:

```bash
# Stop the running container
docker stop api_python

# Remove the container
docker rm api_python
```

---
*Developed by [Marcela Zapata Vanegas](https://www.linkedin.com/in/marcelazapatavanegas/) - Technical Writer & Full Stack Developer.*
