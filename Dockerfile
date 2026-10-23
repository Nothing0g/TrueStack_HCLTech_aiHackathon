FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HF_HOME=/root/.cache/huggingface
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl poppler-utils tesseract-ocr && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app

# Cache the selected embedding model during image build so container startup does not need to download it.
# Set PRELOAD_EMBEDDING_MODEL=0 only for constrained/offline builds with a pre-populated mounted cache.
ARG PRELOAD_EMBEDDING_MODEL=1
RUN if [ "$PRELOAD_EMBEDDING_MODEL" = "1" ]; then python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"; fi

EXPOSE 8000 8501
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
