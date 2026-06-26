# =============================================================================
# MentorMatch — PyInstaller Spec Windows (.exe)
# =============================================================================

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

datas = [
    ('templates',  'templates'),
    ('static',     'static'),
    ('models',     'models'),
]
datas += collect_data_files('sentence_transformers')
datas += collect_data_files('transformers')
datas += collect_data_files('tokenizers')

hidden_imports = [
    'flask', 'jinja2', 'werkzeug', 'click',
    'sklearn', 'sklearn.metrics.pairwise', 'sklearn.utils._cython_blas',
    'sklearn.neighbors._typedefs', 'sklearn.utils._weight_vector',
    'sentence_transformers', 'transformers', 'torch', 'numpy',
    'pandas', 'openpyxl', 'xlrd',
    'requests', 'concurrent.futures',
    'PIL', 'PIL.Image', 'PIL.ImageOps', 'PIL.ImageFilter',
]
hidden_imports += collect_submodules('sentence_transformers')
hidden_imports += collect_submodules('transformers')

a = Analysis(
    ['launcher.py'],
    pathex=[os.getcwd()],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'IPython', 'jupyter', 'notebook', 'cv2', 'PyQt5', 'tkinter'],
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
    strip=False,
    upx=True,
    console=True,   # affiche une fenêtre console (logs visibles)
    icon=None,      # remplace par 'icon.ico' si tu as une icône Windows
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
