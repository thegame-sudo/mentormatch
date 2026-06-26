# =============================================================================
# MentorMatch — PyInstaller Spec File
# =============================================================================
# Ce fichier décrit comment PyInstaller doit assembler l'application .app macOS.
# Lance le build avec : pyinstaller MentorMatch.spec
# =============================================================================

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── Données à inclure dans le bundle ─────────────────────────────────────────
# Chaque tuple : (source_sur_disque, destination_dans_le_bundle)
datas = [
    ('templates',  'templates'),   # templates HTML Flask
    ('static',     'static'),      # fichiers statiques (CSS, JS, images)
    ('models',     'models'),      # modèle CamemBERT pré-téléchargé
]

# Ajoute les fichiers de données des packages sentence_transformers et transformers
datas += collect_data_files('sentence_transformers')
datas += collect_data_files('transformers')
datas += collect_data_files('tokenizers')

# ── Imports cachés ────────────────────────────────────────────────────────────
# PyInstaller ne détecte pas toujours les imports dynamiques (importlib, plugins, etc.)
# On les liste explicitement ici pour les forcer à être inclus.
hidden_imports = [
    # Flask et ses dépendances
    'flask', 'jinja2', 'werkzeug', 'click',
    # Science / ML
    'sklearn', 'sklearn.metrics.pairwise', 'sklearn.utils._cython_blas',
    'sklearn.neighbors._typedefs', 'sklearn.utils._weight_vector',
    'sentence_transformers', 'transformers', 'torch', 'numpy',
    # Lecture des fichiers
    'pandas', 'openpyxl', 'xlrd',
    # Divers
    'requests', 'concurrent.futures',
    # PIL / Pillow (requis par sentence_transformers via CLIPModel)
    'PIL', 'PIL.Image', 'PIL.ImageOps', 'PIL.ImageFilter',
]

# Ajoute tous les sous-modules de sentence_transformers et transformers
hidden_imports += collect_submodules('sentence_transformers')
hidden_imports += collect_submodules('transformers')

# ── Analyse du script principal ───────────────────────────────────────────────
a = Analysis(
    ['launcher.py'],               # point d'entrée de l'application
    pathex=[os.getcwd()],          # chemin de recherche des modules
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclusions pour réduire la taille du bundle
        'matplotlib', 'IPython', 'jupyter', 'notebook',
        'cv2', 'PyQt5', 'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MentorMatch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,    # True = affiche un terminal (utile pour voir les logs)
    codesign_identity=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MentorMatch',
)

# ── Bundle macOS .app ─────────────────────────────────────────────────────────
app = BUNDLE(
    coll,
    name='MentorMatch.app',
    icon=None,          # remplace par 'icon.icns' si tu as une icône
    bundle_identifier='fr.caissedesdepots.mentormatch',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleName': 'MentorMatch',
        'CFBundleDisplayName': 'MentorMatch — alter égales',
    },
)
