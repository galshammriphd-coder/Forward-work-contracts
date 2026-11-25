# ---- frontend build ----
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- application ----
FROM python:3.12-slim
# OCR engine with Arabic data (scanned PDFs), LibreOffice for legacy .doc/.xls, a font with Arabic glyphs for PDF reports
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-ara libreoffice-writer libreoffice-calc fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app/backend/
COPY --from=web /web/dist /app/frontend/dist
ENV PMO_DATA_DIR=/data
RUN useradd --system --uid 10001 pmo && mkdir -p /data && chown pmo /data
USER pmo
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
