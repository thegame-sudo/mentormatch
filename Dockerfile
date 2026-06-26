# =============================================================================
# MENTORMATCH — Dockerfile
# =============================================================================
# Image de base : Python 3.11 slim (légère, sans outils inutiles)
FROM python:3.11-slim

# Métadonnées
LABEL maintainer="MentorMatch" description="Application de matching mentor/mentoré"

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5001 \
    # Dossier de cache pour le modèle CamemBERT (à l'intérieur du conteneur)
    TRANSFORMERS_CACHE=/app/models \
    HF_HOME=/app/models

# Répertoire de travail dans le conteneur
WORKDIR /app

# ── Étape 1 : Installation des dépendances système ──
# build-essential est nécessaire pour compiler certains packages Python (scipy, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Étape 2 : Installation des dépendances Python ──
# On copie d'abord uniquement requirements.txt pour profiter du cache Docker :
# si les dépendances ne changent pas, Docker ne réinstalle pas tout à chaque build.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Étape 3 : Pré-téléchargement du modèle CamemBERT ──
# On télécharge le modèle pendant le build pour qu'il soit inclus dans l'image.
# Ainsi, l'app démarre immédiatement sans accès internet au runtime.
# Note : cela alourdit l'image d'environ 500 Mo.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
print('Téléchargement du modèle CamemBERT...'); \
SentenceTransformer('distiluse-base-multilingual-cased-v2'); \
print('Modèle téléchargé et mis en cache.')"

# ── Étape 4 : Copie du code de l'application ──
# On copie après l'installation des dépendances pour optimiser le cache Docker
COPY app.py .
COPY templates/ templates/
COPY static/ static/

# ── Étape 5 : Exposition du port ──
EXPOSE 5001

# ── Étape 6 : Commande de démarrage ──
# On utilise gunicorn en production (plus stable que le serveur de développement Flask)
# Fallback sur python app.py si gunicorn n'est pas disponible
CMD ["python", "app.py"]
