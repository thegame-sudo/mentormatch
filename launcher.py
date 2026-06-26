"""
MentorMatch — Point d'entrée pour le bundle macOS (.app)

Ce fichier est utilisé par PyInstaller comme script principal.
Il gère :
  - La détection du mode "bundlé" (PyInstaller) vs développement
  - La redirection du modèle CamemBERT vers le dossier bundlé
  - Le reconfiguration des dossiers Flask (templates, static)
  - L'ouverture automatique du navigateur
  - Le lancement du serveur Flask
"""

import sys
import os
import threading
import webbrowser
import time
import socket

PORT = 5001

# ── Verrou single-instance ────────────────────────────────────────────────────
# Si le port est déjà occupé, une instance tourne déjà.
# On ouvre juste le navigateur et on quitte immédiatement.
def port_is_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

if port_is_in_use(PORT):
    webbrowser.open(f'http://localhost:{PORT}')
    sys.exit(0)  # déjà lancé → on ouvre juste le navigateur

# ── Détection du mode d'exécution ─────────────────────────────────────────────
# Quand PyInstaller crée un bundle, sys.frozen = True et les fichiers bundlés
# sont accessibles via sys._MEIPASS (dossier temporaire extrait au démarrage).
if getattr(sys, 'frozen', False):
    BASE = sys._MEIPASS  # chemin vers les fichiers extraits du bundle
else:
    BASE = os.path.dirname(os.path.abspath(__file__))  # mode développement normal

# ── Redirection du cache modèle vers le dossier bundlé ───────────────────────
# Le modèle CamemBERT (~500 Mo) est inclus dans le bundle dans le sous-dossier "models".
# On redirige les variables d'environnement pour que sentence_transformers le trouve.
models_path = os.path.join(BASE, 'models')
os.environ['TRANSFORMERS_CACHE']          = models_path
os.environ['HF_HOME']                     = models_path
os.environ['SENTENCE_TRANSFORMERS_HOME']  = models_path

# ── Import de l'application Flask ────────────────────────────────────────────
sys.path.insert(0, BASE)
import app as mentor_app  # importe app.py (notre backend Flask)

# Reconfigure les dossiers Flask pour pointer vers les bons chemins dans le bundle
mentor_app.app.template_folder = os.path.join(BASE, 'templates')
mentor_app.app.static_folder   = os.path.join(BASE, 'static')

# ── Ouverture automatique du navigateur ──────────────────────────────────────
# On attend 2.5s que le serveur Flask soit prêt avant d'ouvrir le navigateur.
def open_browser():
    time.sleep(2.5)
    webbrowser.open(f'http://localhost:{PORT}')

threading.Thread(target=open_browser, daemon=True).start()

# ── Démarrage du serveur ──────────────────────────────────────────────────────
print("[MentorMatch] Chargement du modèle CamemBERT...")
mentor_app.get_st_model()
print("[MentorMatch] Modèle prêt. Lancement du serveur...")
print("[MentorMatch] Ouvre http://localhost:5001 dans ton navigateur si il ne s'ouvre pas automatiquement.")

# use_reloader=False important : PyInstaller ne supporte pas le reloader Flask
mentor_app.app.run(host='127.0.0.1', port=PORT, debug=False, use_reloader=False)
