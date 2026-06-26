# 🚀 Démarrage Rapide — 5 minutes top chrono !

## 📦 Tu as reçu

```
✅ index_final.html       ← Interface complète (LOCAL + ONLINE)
✅ README_COMPLET.md      ← Documentation détaillée
✅ mentors.csv            ← 30 mentors de test
✅ mentores.csv           ← 30 mentorés de test
```

---

## ⚡ 5 étapes pour lancer l'app

### 1️⃣ Prépare le dossier (1 min)

```bash
# Crée un dossier
mkdir mentor_matching
cd mentor_matching

# Copie-y les fichiers :
# - app.py (tu l'as déjà)
# - index_final.html (renomme en index.html)
# - mentors.csv
# - mentores.csv
# - requirements.txt
```

### 2️⃣ Crée l'environnement Python (1 min)

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

Tu devrais voir `(venv)` devant ta ligne 👍

### 3️⃣ Installe les dépendances (2 min)

```bash
pip install -r requirements.txt
```

Attends que ça finisse (~ 2-3 min selon ta connexion).

### 4️⃣ Lance le serveur (30 sec)

```bash
python app.py
```

Tu devrais voir :
```
 * Running on http://127.0.0.1:5000
```

### 5️⃣ Ouvre l'app (30 sec)

Clique sur http://127.0.0.1:5000

**🎉 C'est lancé !**

---

## 🎯 Première utilisation

### Mode LOCAL (Recommandé)

```
1. Topbar : Sélectionne 🏠 LOCAL
2. Tab "Importer" : Upload mentors.csv + mentores.csv
3. Tab "Configurer" : Laisse par défaut (URL Ollama)
4. Tab "Matching" : [🚀 Lancer matching]
5. Valide/rejette les matchs
6. [⬇ Exporter] Excel
```

**ℹ️ LOCAL fonctionne si tu as Ollama installé**
- Sinon, passe en ONLINE (voir ci-dessous)

### Mode ONLINE (Groq gratuit)

```
1. Topbar : Sélectionne ☁️ ONLINE
2. Tab "Importer" : Upload mentors.csv + mentores.csv
3. Tab "Configurer" :
   ├─ Fournisseur : [Groq ▼]
   ├─ Clé API : rentre gsk_XXXXX
   └─ [💾 Sauvegarder]
4. Tab "Matching" : [🚀 Lancer matching]
5. Valide/rejette les matchs
6. [⬇ Exporter] Excel
```

**Obtenir une clé Groq (gratuit) :**
1. https://console.groq.com
2. Crée compte (email ou Google)
3. Copie ta clé API

---

## 📋 Fichiers CSV

### Format attendu

```
nom,prenom,age,sexe,ville,domaine,attentes
Dupont,Jean,45,M,Paris,Tech,Confiance en soi
```

**Colonnes obligatoires :**
- `nom` : Nom de famille
- `prenom` : Prénom
- `age` : Âge (nombre)
- `sexe` : M ou F
- `ville` : Ville (texte libre)
- `domaine` : Domaine d'expertise (Tech, Marketing, RH, etc.)
- `attentes` : Ce qu'ils cherchent (Leadership, Confiance, etc.)

**Tu as 2 fichiers de test :**
- `mentors.csv` : 30 mentors
- `mentores.csv` : 30 mentorés

---

## ⚠️ Si ça ne marche pas

### "Python not found"
```bash
python --version
# Si erreur → réinstalle Python
# https://www.python.org
```

### "Module not found"
```bash
pip install flask pandas openpyxl anthropic requests torch transformers sentencepiece
```

### "Port 5000 déjà utilisé"
```bash
# Change le port dans app.py :
# app.run(port=5001, debug=True)
```

### "Erreur LOCAL (Ollama)"
```
❌ "Connection refused"
→ Ollama n'est pas lancé
→ Télécharge Ollama : https://ollama.ai
→ Fais : ollama pull mistral:7b
→ Puis : ollama serve
```

### "Erreur ONLINE (API)"
```
❌ "Unauthorized 401"
→ Clé API invalide
→ Généré une nouvelle clé sur console.groq.com

❌ "Rate limit"
→ Groq gratuit : 30 appels/minute
→ Attends 30 sec et réessaye
```

---

## 🎨 Interface

### Topbar
```
🎯 MentorMatch  [🏠 LOCAL | ☁️ ONLINE]  [🌙] [⬇ Export]
```

### 3 Tabs
```
1️⃣ Importer    → Upload CSV
2️⃣ Configurer  → Config (LOCAL/ONLINE)
3️⃣ Matching    → Résultats + validation
```

### Matching Results
```
[Avatar] Mentor          [Score]  [Avatar] Mentoré    [✓] [✕]
         Domaine · Ville          Domaine · Ville

Exemple :
[JD] Jean Dupont (Tech)  [87%]    [EL] Emma Leroy     [✓] [✕]
     Paris               Raison : mixité ✓ · attentes ✓
```

---

## 🔄 Workflow complet

```
1. Lance app.py
   ↓
2. Ouvre http://localhost:5000
   ↓
3. Choisis MODE (LOCAL ou ONLINE)
   ↓
4. Upload mentors.csv + mentores.csv
   ↓
5. Configure (Ollama URL ou API Key)
   ↓
6. Lance matching 🚀
   ↓
7. Vois les résultats avec scores
   ↓
8. Valide/rejette les matchs
   ↓
9. Exporte Excel 📊
```

---

## 📚 Après le démarrage rapide

Pour plus de détails, lis :
- **README_COMPLET.md** → Installation complète + troubleshooting
- **ONLINE_MODE_GUIDE.md** → Mode ONLINE avancé
- **DEMO_GUIDE.md** → Exploration interface

---

## 🎯 Checklist avant de commencer

```
☐ Python 3.8+ installé
☐ Dossier mentor_matching créé
☐ Fichiers copiés dedans
☐ Environnement virtuel activé (venv)
☐ pip install -r requirements.txt fait
☐ python app.py lancé
☐ http://localhost:5000 ouvert

✅ Tu es prêt !
```

---

## 🚀 C'est parti !

```bash
# Copy-paste ces 3 lignes :
source venv/bin/activate  # (Windows: venv\Scripts\activate)
python app.py
# Ouvre http://localhost:5000
```

**Bon matching ! 🎯**

Des questions ? Lire README_COMPLET.md 📖
