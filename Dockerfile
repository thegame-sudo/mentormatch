# =============================================================================
# AlterEgale Match — Dockerfile (compatible Hugging Face Spaces)
# =============================================================================
FROM python:3.11-slim

LABEL maintainer="AlterEgale Match" description="Application de matching mentor/mentoré Fides 10"

# Port 7860 obligatoire pour Hugging Face Spaces
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    TRANSFORMERS_CACHE=/app/models \
    HF_HOME=/app/models \
    SENTENCE_TRANSFORMERS_HOME=/app/models

WORKDIR /app

# ── Dépendances système ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# ── Dépendances Python ──
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Pré-téléchargement du modèle CamemBERT ──
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
print('Téléchargement du modèle...'); \
SentenceTransformer('distiluse-base-multilingual-cased-v2'); \
print('Modèle prêt.')"

# ── Copie du code ──
COPY app.py .
COPY templates/ templates/
COPY static/ static/

# ── Utilisateur non-root (requis par Hugging Face Spaces) ──
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# ── Port Hugging Face Spaces ──
EXPOSE 7860

CMD ["python", "app.py"]
