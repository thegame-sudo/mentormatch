#!/bin/bash
# =============================================================================
# MentorMatch — Script de build macOS
# =============================================================================
# Lance ce script depuis le dossier files/ :
#   chmod +x build_mac.sh
#   ./build_mac.sh
#
# Résultat : dist/MentorMatch.app — double-clique pour lancer l'application
# =============================================================================

set -e  # arrête le script si une commande échoue
cd "$(dirname "$0")"  # se place dans le dossier du script

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  MentorMatch — Build macOS .app"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── Étape 1 : Vérification des dépendances ───────────────────────────────────
echo "[1/4] Vérification des dépendances Python..."
pip install -q flask pandas openpyxl requests numpy sentence-transformers scikit-learn pyinstaller

# ── Étape 2 : Téléchargement du modèle CamemBERT ────────────────────────────
echo ""
echo "[2/4] Téléchargement du modèle CamemBERT dans ./models/ ..."
python3 - <<'PYEOF'
import os
os.makedirs('models', exist_ok=True)
os.environ['SENTENCE_TRANSFORMERS_HOME'] = './models'
from sentence_transformers import SentenceTransformer
SentenceTransformer('distiluse-base-multilingual-cased-v2', cache_folder='./models')
print("    Modèle prêt !")
PYEOF

# ── Étape 3 : Build PyInstaller ───────────────────────────────────────────────
echo ""
echo "[3/4] Build de l'application avec PyInstaller..."
echo "    (peut prendre 5-10 minutes la première fois)"
echo ""
pyinstaller MentorMatch.spec --clean --noconfirm

# ── Étape 4 : Résultat ───────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ Build terminé !"
echo ""
echo "  Ton application : dist/MentorMatch.app"
echo ""
echo "  Pour lancer : double-clique sur MentorMatch.app"
echo "  Ou depuis le terminal : open dist/MentorMatch.app"
echo "═══════════════════════════════════════════════════════"
echo ""
