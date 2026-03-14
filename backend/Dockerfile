FROM python:3.11-slim

# System deps for PostGIS / Shapely
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgeos-dev libproj-dev gdal-bin libgdal-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
