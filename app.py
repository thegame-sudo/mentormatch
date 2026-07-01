# =============================================================================
# MENTORMATCH — Backend Flask
# =============================================================================
# Application de matching mentor/mentoré.
# Fonctionnement général :
#   1. L'utilisateur importe deux fichiers CSV/Excel (mentors + mentorés)
#   2. L'app calcule un score de compatibilité pour chaque paire possible
#   3. L'utilisateur valide ou refuse chaque proposition
#   4. Les matchs validés peuvent être exportés en Excel
#
# Moteurs de scoring disponibles :
#   - CamemBERT : modèle de NLP local, rapide, toujours disponible
#   - Ollama     : LLM local (Mistral 7B), plus lent mais plus nuancé
#   - Mistral API: LLM en ligne via API, qualité maximale
#   - Compare    : CamemBERT + Ollama en parallèle pour comparer les deux
# =============================================================================

from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd       # lecture des fichiers CSV et Excel
import json               # sérialisation des données pour les LLM
import io                 # gestion du fichier Excel en mémoire pour l'export
import os                 # lecture des variables d'environnement (PORT)
import requests           # appels HTTP vers Ollama et Mistral API
import concurrent.futures # exécution parallèle des calculs de score
import warnings
warnings.filterwarnings("ignore")  # supprime les avertissements non critiques

# --- Application Flask ---
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # taille max des fichiers uploadés : 16 Mo

# =============================================================================
# STOCKAGE EN MÉMOIRE (état global de l'application)
# =============================================================================
# Toutes les données sont stockées ici pendant la session.
# ATTENTION : ces données sont perdues si le serveur redémarre.
# Pour une version production, il faudrait une base de données.

data_store = {
    "mentors": [],         # liste des mentors chargés depuis le fichier
    "mentores": [],        # liste des mentorés chargés depuis le fichier
    "matches": [],         # propositions de matching en cours (en attente de validation)
    "validated": [],       # matchs validés définitivement par l'utilisateur
    "rejected_pairs": set(), # ensemble des paires refusées (blacklist)
                             # format : {(key_mentor, key_mentore), ...}
                             # ces paires ne seront plus reproposées lors d'un rematch
}

# =============================================================================
# UTILITAIRES
# =============================================================================

def key(p):
    """
    Génère une clé unique pour identifier une personne (mentor ou mentoré).
    Utilise (nom, prenom) en minuscules pour éviter les doublons dus à la casse.
    """
    return (str(p.get('nom', '')).strip().lower(), str(p.get('prenom', '')).strip().lower())

# Catégories d'attentes définies dans le formulaire Fides
ATTENTES_CATEGORIES = [
    "Evoluer et gagner en agilité dans un environnement en transformation",
    "Mieux connaître le Groupe, ses enjeux, sa culture",
    "Réfléchir à soi / son savoir être / sa posture professionnelle",
]

def parse_categories(val):
    """
    Convertit une chaîne de catégories séparées par des virgules en ensemble normalisé.
    Ex: "Mieux connaître le Groupe, Réfléchir à soi" → {"mieux connaître le groupe", "réfléchir à soi"}
    """
    if not val:
        return set()
    return {c.strip().lower() for c in str(val).split(',') if c.strip()}

def tranche_to_int(t):
    """
    Extrait la borne inférieure d'une tranche d'âge.
    Ex: "35-40" → 35 | "55+" → 55 | "50-55" → 50
    """
    try:
        return int(str(t).split('-')[0].replace('+', '').strip())
    except:
        return 0

def anciennete_to_int(a):
    """
    Extrait la borne inférieure d'une ancienneté.
    Gère les formats : "5-10 ans" | "5 à 10 ans" | "10+" | "Moins de 5 ans" | "Plus de 20 ans"
    """
    try:
        s = str(a).lower().strip()
        s = s.replace('plus de ', '').replace('moins de ', '').replace(' ans', '').replace('+', '')
        # Format "10 à 15" ou "10-15"
        for sep in [' à ', '-']:
            if sep in s:
                return int(s.split(sep)[0].strip())
        return int(s.strip())
    except:
        return 0

# =============================================================================
# MAPPING DES COLONNES — conversion des noms réels Fides vers les noms internes
# =============================================================================
# Les fichiers Excel Fides utilisent des libellés longs avec accents et espaces.
# On les mappe vers des noms courts utilisés en interne par l'application.

COLUMNS_MAP = {
    # Colonnes communes mentors et mentorés
    'Nom':                      'nom',
    'Prénom':                   'prenom',
    'Vous êtes':                'sexe',        # valeurs : "Un homme" / "Une femme"
    "Tranche d'âge":            'tranche_age', # ex: "45-49 ans"
    'Ville (professionnelle)':  'ville',
    'Région':                   'region',
    'Ancienneté dans le Groupe':'anciennete',  # ex: "10 à 15 ans"
    'Votre entité':             'entite',
    'Votre filière':            'filiere',
    # Colonnes spécifiques aux mentors
    "Pourquoi souhaitez-vous mentorer quelqu'un et partager votre expérience ?": 'motivation',
    "Attentes des mentoré(e)s pour lesquelles vous pouvez apporter un soutien":  'attentes_supportees',
    # Colonnes spécifiques aux mentorés
    'Attentes en tant que Mentoré(e)':  'attentes_categories',
    'Précisions sur les attentes':      'attentes_texte',
    "Comment imaginez-vous votre Mentor(e) ?": 'mentor_attendu',
}

def normalize_sexe(val):
    """
    Normalise les valeurs de sexe du formulaire Fides.
    "Un homme" / "Homme" → "Homme" | "Une femme" / "Femme" → "Femme"
    """
    v = str(val).strip().lower()
    if 'homme' in v or 'man' in v or v == 'm':
        return 'Homme'
    if 'femme' in v or 'woman' in v or v == 'f':
        return 'Femme'
    return str(val).strip()

def normalize_tranche_age(val):
    """
    Normalise les tranches d'âge Fides.
    "45-49 ans" → "45-49" | "Moins de 30 ans" → "0-30" | déjà normalisé → tel quel
    """
    s = str(val).strip()
    s = s.replace(' ans', '').replace(' an', '')
    # "Moins de 30" → "0-30"
    if 'moins de' in s.lower():
        n = ''.join(filter(str.isdigit, s))
        return f"0-{n}"
    return s

def normalize_anciennete(val):
    """
    Normalise les anciennetés Fides.
    "10 à 15 ans" → "10-15 ans" (format cohérent pour anciennete_to_int)
    """
    return str(val).strip().replace(' à ', '-')

def map_and_normalize(df):
    """
    Applique le mapping de colonnes et les normalisations sur un DataFrame Fides.
    Renomme les colonnes et normalise les valeurs de sexe, tranche_age, anciennete.
    """
    # Renommage des colonnes connues (les colonnes inconnues sont conservées telles quelles)
    rename = {k: v for k, v in COLUMNS_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Normalisation des valeurs
    if 'sexe'        in df.columns: df['sexe']        = df['sexe'].apply(normalize_sexe)
    if 'tranche_age' in df.columns: df['tranche_age'] = df['tranche_age'].apply(normalize_tranche_age)
    if 'anciennete'  in df.columns: df['anciennete']  = df['anciennete'].apply(normalize_anciennete)

    # Si "Autre entité, précisez" est renseigné, l'utiliser comme entité principale
    if 'Autre entité, précisez' in df.columns and 'entite' in df.columns:
        mask = df['Autre entité, précisez'].notna() & (df['Autre entité, précisez'] != '')
        df.loc[mask, 'entite'] = df.loc[mask, 'Autre entité, précisez']

    # Idem pour "Autre filière, précisez"
    if 'Autre filière, précisez' in df.columns and 'filiere' in df.columns:
        mask = df['Autre filière, précisez'].notna() & (df['Autre filière, précisez'] != '')
        df.loc[mask, 'filiere'] = df.loc[mask, 'Autre filière, précisez']

    return df


# =============================================================================
# ENSEMBLE TEXT MINING — CamemBERT + TF-IDF + BM25
# =============================================================================
# On combine trois modèles complémentaires pour scorer la similarité
# entre les textes libres du mentor (motivation) et du mentoré (attentes_texte).
#
# Pourquoi trois modèles ?
#   - CamemBERT : comprend le SENS des phrases (sémantique profonde)
#     Ex: "développer ma confiance" ≈ "gagner en assurance" → score élevé
#   - TF-IDF    : mesure l'OVERLAP de mots-clés (similarité lexicale)
#     Ex: deux textes avec "leadership" et "équipe" → score élevé
#   - BM25      : algorithme de recherche (Google-style), pondère les mots rares
#     Ex: un mot rare commun aux deux textes → score très élevé
#
# Ensemble = moyenne pondérée des trois → plus robuste qu'un seul modèle

def tfidf_score(text1, text2):
    """
    Calcule la similarité cosinus TF-IDF entre deux textes.
    TF-IDF transforme chaque texte en vecteur de mots pondérés par leur fréquence.
    Retourne un score entre 0 et 100.
    Avantage : rapide, sensible aux mots-clés communs.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        if not text1.strip() or not text2.strip():
            return 50
        # On vectorise les deux textes ensemble pour avoir un espace commun
        vec = TfidfVectorizer(min_df=1, analyzer='word', ngram_range=(1, 2))
        mat = vec.fit_transform([text1, text2])
        score = cosine_similarity(mat[0], mat[1])[0][0] * 100
        return int(score)
    except:
        return 50

def bm25_score(text1, text2):
    """
    Calcule un score BM25 bidirectionnel entre deux textes.
    BM25 (Best Match 25) est l'algorithme de ranking utilisé par les moteurs
    de recherche — il pondère les mots rares plus fortement que les mots communs.

    On le calcule dans les deux sens (text1 → text2 ET text2 → text1) puis
    on fait la moyenne pour obtenir un score symétrique.
    Retourne un score entre 0 et 100.
    """
    try:
        from rank_bm25 import BM25Okapi
        import re

        def tokenize(t):
            # Tokenisation simple : minuscules, on garde les mots de 2+ caractères
            return [w for w in re.findall(r'\b\w{2,}\b', t.lower()) if w]

        t1, t2 = tokenize(text1), tokenize(text2)
        if not t1 or not t2:
            return 50

        # Sens 1 : text1 comme corpus, text2 comme requête
        bm1 = BM25Okapi([t1])
        s1  = bm1.get_scores(t2)[0]

        # Sens 2 : text2 comme corpus, text1 comme requête
        bm2 = BM25Okapi([t2])
        s2  = bm2.get_scores(t1)[0]

        # Moyenne des deux directions → score symétrique
        raw = (s1 + s2) / 2

        # Normalisation : BM25 produit des scores typiquement entre 0 et 10
        # pour des textes courts. On scale vers [0, 100] avec une sigmoïde douce.
        import math
        normalized = 100 / (1 + math.exp(-(raw - 2) * 0.8))
        return int(min(100, max(0, normalized)))
    except:
        return 50

def ensemble_text_score(text_mentor, text_mentore):
    """
    Score d'ensemble combinant CamemBERT + TF-IDF + BM25.
    Chaque modèle apporte une perspective différente :
        - CamemBERT (50%) : sens sémantique profond
        - BM25       (30%) : pertinence des mots-clés rares
        - TF-IDF     (20%) : overlap lexical général

    Retourne un score entre 0 et 100.
    """
    t1 = str(text_mentor).strip()
    t2 = str(text_mentore).strip()

    # Si l'un des textes est vide, score neutre
    if not t1 or not t2:
        return 50

    # ── CamemBERT : similarité sémantique ──────────────────────────────────
    try:
        from sklearn.metrics.pairwise import cosine_similarity
        model = get_st_model()
        e1 = model.encode(t1)
        e2 = model.encode(t2)
        camembert = int(cosine_similarity([e1], [e2])[0][0] * 100)
    except:
        camembert = 50

    # ── TF-IDF : overlap de mots-clés ──────────────────────────────────────
    tfidf = tfidf_score(t1, t2)

    # ── BM25 : pertinence des termes rares ─────────────────────────────────
    bm25 = bm25_score(t1, t2)

    # ── Moyenne pondérée ───────────────────────────────────────────────────
    # CamemBERT a le plus de poids car il comprend le sens, pas seulement les mots
    score = int(camembert * 0.50 + bm25 * 0.30 + tfidf * 0.20)

    print(f"[Ensemble] CamemBERT={camembert} TF-IDF={tfidf} BM25={bm25} → {score}")
    return score


# =============================================================================
# MODÈLE CAMEMBERT — chargement unique en mémoire
# =============================================================================
# Le modèle sentence_transformers est lourd (plusieurs centaines de Mo).
# On le charge une seule fois au démarrage et on le réutilise pour tous les calculs.
# Sans ce cache, le modèle serait rechargé à chaque paire → très lent.

_st_model = None  # variable globale pour stocker le modèle en cache

def get_st_model():
    """
    Retourne le modèle CamemBERT en le chargeant depuis le disque si nécessaire.
    Le modèle 'distiluse-base-multilingual-cased-v2' est multilingue (français inclus)
    et optimisé pour calculer la similarité sémantique entre deux phrases.
    """
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer('distiluse-base-multilingual-cased-v2')
    return _st_model


# =============================================================================
# MOTEUR 1 : CAMEMBERT (local, toujours disponible)
# =============================================================================

def score_camembert(mentor, mentore, weights):
    """
    Calcule le score de compatibilité entre un mentor et un mentoré.
    Adapté au formulaire Fides 10 — Caisse des Dépôts / alter égales.

    Champs utilisés :
        Communs  : sexe, tranche_age, region, entite, filiere, anciennete
        Mentor   : attentes_supportees (catégories qu'il peut couvrir), motivation
        Mentoré  : attentes_categories (ses 3 besoins max), attentes_texte

    Critères de scoring :
        1. Attentes   : % catégories mentoré couverts par mentor + similarité CamemBERT
        2. Sexe       : mixité H/F recommandée
        3. Tranche âge: mentor plus âgé = bonus
        4. Filière    : filières différentes = complémentarité
        5. Entité     : entités différentes = cross-entité valorisé
        6. Ancienneté : mentor plus senior = bonus
        7. Région     : même région = facilite les échanges

    Retourne :
        (score, raison) — score ∈ [10, 100], raison = explication textuelle
    """

    # ── Critère 1 : Attentes ──────────────────────────────────────────────────
    # 1a. Correspondance catégorielle : quel % des besoins du mentoré
    #     le mentor déclare pouvoir couvrir ?
    #     Ex: mentoré veut [A, B, C] et mentor supporte [A, C] → 2/3 = 67%
    ment_cats  = parse_categories(mentore.get('attentes_categories', ''))
    support    = parse_categories(mentor.get('attentes_supportees', ''))
    if ment_cats:
        intersection    = ment_cats & support     # catégories en commun
        coverage_score  = int(len(intersection) / len(ment_cats) * 100)
    else:
        coverage_score  = 50  # pas de catégorie déclarée : score neutre

    # 1b. Score ensemble sur les textes libres (motivation mentor vs attentes_texte mentoré)
    #     On utilise CamemBERT + TF-IDF + BM25 en parallèle pour un score plus robuste.
    #     CamemBERT comprend le sens, TF-IDF et BM25 mesurent l'overlap de mots-clés.
    t_mentor  = str(mentor.get('motivation', mentor.get('attentes_supportees', '')))
    t_mentore = str(mentore.get('attentes_texte', mentore.get('attentes_categories', '')))
    semantic_score = ensemble_text_score(t_mentor, t_mentore)

    # Score d'attentes final = moyenne pondérée couverture catégorielle + ensemble texte
    # La couverture catégorielle est très fiable (données structurées) → poids plus élevé
    attentes_score = int(coverage_score * 0.55 + semantic_score * 0.45)

    # ── Critère 2 : Mixité H/F ────────────────────────────────────────────────
    # La mixité est recommandée dans le programme alter égales.
    # Différence de sexe → 80, même sexe → 40
    s_mentor  = str(mentor.get('sexe', '')).strip().lower()
    s_mentore = str(mentore.get('sexe', '')).strip().lower()
    sexe_score = 80 if s_mentor != s_mentore else 40

    # ── Critère 3 : Tranche d'âge ────────────────────────────────────────────
    # Le mentor doit être dans une tranche d'âge supérieure au mentoré.
    # On extrait la borne basse de la tranche pour comparer.
    # Ex: "40-45" vs "30-35" → mentor plus âgé → 80
    age_m = tranche_to_int(mentor.get('tranche_age', '0'))
    age_e = tranche_to_int(mentore.get('tranche_age', '0'))
    if age_m > age_e:
        tranche_score = 80      # mentor nettement plus âgé
    elif age_m == age_e:
        tranche_score = 50      # même tranche → acceptable
    else:
        tranche_score = 15      # mentor plus jeune → mauvais signe

    # ── Critère 4 : Filière ──────────────────────────────────────────────────
    # Complémentarité recherchée : filières DIFFÉRENTES = plus de valeur d'échange.
    # Ex: mentor Finance + mentoré RH → apport d'une perspective externe
    f_mentor  = str(mentor.get('filiere', '')).strip().lower()
    f_mentore = str(mentore.get('filiere', '')).strip().lower()
    filiere_score = 70 if f_mentor and f_mentore and f_mentor != f_mentore else 50

    # ── Critère 5 : Entité ───────────────────────────────────────────────────
    # Cross-entité valorisé : mentors d'une autre entité apportent une vision externe.
    e_mentor  = str(mentor.get('entite', '')).strip().lower()
    e_mentore = str(mentore.get('entite', '')).strip().lower()
    entite_score = 70 if e_mentor and e_mentore and e_mentor != e_mentore else 50

    # ── Critère 6 : Ancienneté ───────────────────────────────────────────────
    # Un mentor plus senior (plus d'années d'expérience) apporte plus de valeur.
    anc_m = anciennete_to_int(mentor.get('anciennete', '0'))
    anc_e = anciennete_to_int(mentore.get('anciennete', '0'))
    if anc_m > anc_e:
        anciennete_score = 80   # mentor plus senior → idéal
    elif anc_m == anc_e:
        anciennete_score = 50   # même ancienneté → acceptable
    else:
        anciennete_score = 20   # mentor moins senior → peu souhaitable

    # ── Critère 7 : Région ───────────────────────────────────────────────────
    # La même région facilite les rencontres physiques éventuelles.
    r_mentor  = str(mentor.get('region', '')).strip().lower()
    r_mentore = str(mentore.get('region', '')).strip().lower()
    region_score = 80 if r_mentor and r_mentore and r_mentor == r_mentore else 40

    # ── Score pondéré final ──────────────────────────────────────────────────
    # Chaque critère est multiplié par son poids (configurable dans les paramètres).
    w = {
        'attentes':   weights.get('attentes',   5),
        'sexe':       weights.get('sexe',       3),
        'tranche_age':weights.get('tranche_age',4),
        'filiere':    weights.get('filiere',    3),
        'entite':     weights.get('entite',     2),
        'anciennete': weights.get('anciennete', 4),
        'region':     weights.get('region',     3),
    }
    total_weight = sum(w.values()) or 1
    score = int(
        (attentes_score    * w['attentes']    +
         sexe_score        * w['sexe']        +
         tranche_score     * w['tranche_age'] +
         filiere_score     * w['filiere']     +
         entite_score      * w['entite']      +
         anciennete_score  * w['anciennete']  +
         region_score      * w['region'])
        / total_weight
    )

    # ── Explication textuelle du score ───────────────────────────────────────
    raisons = []
    if sexe_score        > 60: raisons.append("Mixité H/F")
    if tranche_score     > 70: raisons.append("Âge ✓")
    if filiere_score     > 60: raisons.append("Filières complémentaires")
    if entite_score      > 60: raisons.append("Cross-entité")
    if anciennete_score  > 70: raisons.append("Mentor senior")
    if region_score      > 70: raisons.append("Même région")
    if coverage_score    > 60: raisons.append(f"Attentes couvertes à {coverage_score}%")

    return min(100, max(10, score)), " · ".join(raisons) if raisons else "Score calculé"


# =============================================================================
# MOTEUR 2 : OLLAMA (LLM local, nécessite Ollama installé sur la machine)
# =============================================================================

def score_ollama(mentor, mentore, weights, url):
    """
    Affine le score CamemBERT en demandant à un LLM local (Mistral 7B via Ollama)
    d'évaluer la pertinence du match.

    Fonctionnement :
        1. On calcule d'abord le score CamemBERT comme base de référence
        2. On envoie un prompt à Ollama avec les données des deux personnes
        3. Le LLM retourne un score affiné et une raison en JSON
        4. En cas d'échec, on retombe sur le score CamemBERT (fallback)

    Paramètres :
        url : URL de l'instance Ollama locale (défaut: http://localhost:11434)
    """
    # Score de base CamemBERT utilisé comme référence dans le prompt
    base, _ = score_camembert(mentor, mentore, weights)

    # Prompt envoyé au LLM pour affiner le score (champs Fides 10 alter égales)
    prompt = f"""Expert RH programme mentorat alter égales (Caisse des Dépôts).
Évalue la compatibilité mentor/mentoré selon ces critères :
- Mixité H/F recommandée
- Mentor plus senior et plus âgé
- Filières différentes (complémentarité)
- Entités différentes (cross-entité valorisé)
- Même région pour les échanges
- Attentes du mentoré couvertes par le mentor

Mentor: {json.dumps(mentor, ensure_ascii=False)}
Mentoré: {json.dumps(mentore, ensure_ascii=False)}
Score base CamemBERT: {base}/100
Réponds UNIQUEMENT JSON: {{"score": <0-100>, "raison": "<phrase courte en français>"}}"""

    try:
        # Appel à l'API locale d'Ollama (modèle Mistral 7B)
        r = requests.post(
            f"{url}/api/generate",
            json={"model": "mistral:7b", "prompt": prompt, "stream": False},
            timeout=30  # on attend max 30 secondes la réponse du LLM
        )
        if r.status_code == 200:
            text = r.json().get('response', '')
            # Extraction du bloc JSON dans la réponse texte du LLM
            s, e = text.find("{"), text.rfind("}") + 1
            if s >= 0 and e > s:
                p = json.loads(text[s:e])
                return int(p.get("score", base)), p.get("raison", "Ollama")
    except Exception as ex:
        print(f"[Ollama] Erreur: {ex}")

    # Fallback : retourne le score CamemBERT si Ollama est indisponible
    return base, "CamemBERT (Ollama indisponible)"


# =============================================================================
# MOTEUR 3 : MISTRAL API (LLM en ligne, nécessite une clé API)
# =============================================================================

_mistral_last_call = 0  # timestamp du dernier appel Mistral (pour le rate limiting)
_mistral_min_delay  = 2.0  # délai minimum en secondes entre deux appels Mistral
                            # plan gratuit ≈ 5 req/min → 12s d'écart recommandé
                            # plan payant → peut être réduit à 0.5s

def score_mistral(mentor, mentore, weights, api_key):
    """
    Affine le score CamemBERT en utilisant l'API Mistral AI (modèle mistral-large).

    Fonctionnement identique à score_ollama mais via l'API cloud Mistral.
    Inclut une logique de retry automatique en cas de rate limit (erreur 429),
    et un délai proactif entre chaque appel pour éviter le rate limit.

    Limites :
        - Nécessite une clé API valide (https://console.mistral.ai/)
        - Limité en nombre d'appels/minute selon le plan souscrit
        - Conseil : n'utiliser que pour affiner le TOP des résultats CamemBERT
    """
    import time
    global _mistral_last_call

    # Délai proactif : on attend si le dernier appel est trop récent
    # Cela évite le rate limit AVANT qu'il ne se produise
    elapsed = time.time() - _mistral_last_call
    if elapsed < _mistral_min_delay:
        wait = _mistral_min_delay - elapsed
        print(f"[Mistral] Pause {wait:.1f}s pour respecter le rate limit...")
        time.sleep(wait)
    _mistral_last_call = time.time()

    # Score de base CamemBERT utilisé comme référence dans le prompt
    base, _ = score_camembert(mentor, mentore, weights)

    # Prompt envoyé à Mistral pour affiner le score (champs Fides 10 alter égales)
    prompt = f"""Expert RH programme mentorat alter égales (Caisse des Dépôts).
Évalue la compatibilité mentor/mentoré selon ces critères :
- Mixité H/F recommandée
- Mentor plus senior et dans une tranche d'âge supérieure
- Filières différentes (complémentarité externe valorisée)
- Entités différentes (cross-entité = gain de perspective)
- Même région pour faciliter les échanges
- Attentes catégorielles du mentoré couvertes par les compétences déclarées du mentor
- Cohérence entre la motivation du mentor et les attentes textuelles du mentoré

Mentor: {json.dumps(mentor, ensure_ascii=False)}
Mentoré: {json.dumps(mentore, ensure_ascii=False)}
Score base CamemBERT: {base}/100
Réponds UNIQUEMENT JSON: {{"score": <0-100>, "raison": "<phrase courte en français>"}}"""

    # On essaie jusqu'à 3 fois en cas de rate limit (erreur 429)
    for attempt in range(3):
        try:
            r = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",  # clé API dans le header
                    "Content-Type": "application/json"
                },
                json={
                    "model": "mistral-large-latest",  # modèle le plus performant de Mistral
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 150  # réponse courte (juste le JSON)
                },
                timeout=30
            )

            if r.status_code == 200:
                # Succès : on extrait le JSON de la réponse
                text = r.json()["choices"][0]["message"]["content"]
                s, e = text.find("{"), text.rfind("}") + 1
                if s >= 0 and e > s:
                    p = json.loads(text[s:e])
                    return int(p.get("score", base)), p.get("raison", "Mistral")

            elif r.status_code == 429:
                # Rate limit atteint → on attend de plus en plus longtemps avant de réessayer
                # Tentative 1 : attente 1s, tentative 2 : 2s, tentative 3 : 4s
                wait = 2 ** attempt
                print(f"[Mistral] Rate limit (429) — attente {wait}s avant retry {attempt+1}/3")
                time.sleep(wait)

            else:
                # Autre erreur HTTP (401 clé invalide, 500 erreur serveur, etc.)
                print(f"[Mistral] Status {r.status_code}: {r.text[:300]}")
                break  # pas la peine de réessayer

        except Exception as ex:
            print(f"[Mistral] Erreur réseau: {ex}")
            break

    # Fallback : retourne le score CamemBERT si Mistral est indisponible
    return base, "CamemBERT (Mistral indisponible)"


# =============================================================================
# STATISTIQUES — calcul de l'état courant du pool
# =============================================================================

def compute_stats():
    """
    Calcule et retourne les statistiques actuelles de l'application :
        - Nombre total et disponible de mentors/mentorés
        - Nombre de matchs validés et en attente
        - Pourcentage de personnes encore disponibles pour un rematch

    Une personne est "disponible" si elle n'a pas encore été validée dans un match.
    Les personnes dont le match a été refusé restent disponibles (elles peuvent être
    rematché avec quelqu'un d'autre).
    """
    total_m = len(data_store["mentors"])
    total_e = len(data_store["mentores"])

    # Clés des personnes déjà validées dans un match (elles quittent le pool)
    val_mk = {key(v["mentor"]) for v in data_store["validated"]}
    val_ek = {key(v["mentore"]) for v in data_store["validated"]}

    # Compte les personnes encore disponibles (non validées)
    avail_m = sum(1 for m in data_store["mentors"] if key(m) not in val_mk)
    avail_e = sum(1 for m in data_store["mentores"] if key(m) not in val_ek)

    return {
        "total_mentors":    total_m,
        "total_mentores":   total_e,
        "available_mentors":  avail_m,
        "available_mentores": avail_e,
        "validated": len(data_store["validated"]),
        "pending":   len(data_store["matches"]),
        # Pourcentage de disponibilité pour les jauges dans l'interface
        "pct_mentors":  round(avail_m / total_m * 100) if total_m else 0,
        "pct_mentores": round(avail_e / total_e * 100) if total_e else 0,
    }


# =============================================================================
# ROUTES FLASK
# =============================================================================

@app.route("/")
def index():
    """Page principale : sert le fichier HTML de l'interface."""
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    """
    Reçoit un fichier CSV ou Excel uploadé par l'utilisateur.
    Vérifie que les colonnes requises sont présentes, puis stocke les données.

    Paramètres du formulaire :
        file : le fichier uploadé
        type : "mentor" ou "mentore" pour savoir dans quel pool stocker

    Colonnes obligatoires : nom, prenom, age, sexe, ville, domaine, attentes
    """
    file = request.files.get('file')
    ftype = request.form.get('type')  # "mentor" ou "mentore"

    if not file:
        return jsonify({"error": "Aucun fichier fourni"}), 400

    try:
        # Lecture du fichier selon son extension
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        elif file.filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file)
        else:
            return jsonify({"error": "Format non supporté (CSV ou Excel)"}), 400

        # Mapping des noms de colonnes réels Fides → noms internes de l'application
        # (gère aussi bien les fichiers avec les vrais noms Fides que les CSV déjà normalisés)
        df = map_and_normalize(df)

        # Vérification que les colonnes clés sont bien présentes après mapping
        common_cols = ['nom', 'prenom', 'sexe', 'tranche_age', 'region', 'entite', 'filiere', 'anciennete']
        extra_cols = {
            'mentor':  ['attentes_supportees'],
            'mentore': ['attentes_categories'],
        }
        required = common_cols + extra_cols.get(ftype, [])
        missing = set(required) - set(df.columns)
        if missing:
            return jsonify({"error": f"Colonnes manquantes : {', '.join(sorted(missing))}"}), 400

        # Conversion en liste de dictionnaires (un dict par personne)
        # fillna('') remplace les valeurs vides par des chaînes vides
        records = df.fillna('').to_dict('records')

        # Stockage dans le bon pool selon le type
        if ftype == 'mentor':
            data_store['mentors'] = records
        else:
            data_store['mentores'] = records

        return jsonify({"count": len(records), "preview": records[:2]})

    except Exception as ex:
        return jsonify({"error": str(ex)}), 400


@app.route("/demo", methods=["POST"])
def demo():
    """
    Charge des données de démonstration (4 mentors + 4 mentorés fictifs).
    Réinitialise aussi les matchs et validations en cours.
    Utile pour tester l'application sans avoir de vrais fichiers.
    """
    # Données de démo adaptées au formulaire Fides 10 — alter égales (Caisse des Dépôts)
    # Catégories d'attentes possibles :
    #   A = "Evoluer et gagner en agilité dans un environnement en transformation"
    #   B = "Mieux connaître le Groupe, ses enjeux, sa culture"
    #   C = "Réfléchir à soi / son savoir être / sa posture professionnelle"
    data_store['mentors'] = [
        {
            "nom": "Dupont", "prenom": "Jean", "sexe": "Homme",
            "tranche_age": "45-50", "ville": "Paris", "region": "Île-de-France",
            "entite": "CDC Habitat", "filiere": "Finance",
            "anciennete": "15-20 ans",
            "attentes_supportees": "Evoluer et gagner en agilité dans un environnement en transformation,Réfléchir à soi / son savoir être / sa posture professionnelle",
            "motivation": "J'ai traversé de nombreuses transformations organisationnelles et souhaite transmettre mes apprentissages en matière d'agilité et de leadership."
        },
        {
            "nom": "Martin", "prenom": "Sophie", "sexe": "Femme",
            "tranche_age": "40-45", "ville": "Lyon", "region": "Auvergne-Rhône-Alpes",
            "entite": "Bpifrance", "filiere": "RH",
            "anciennete": "10-15 ans",
            "attentes_supportees": "Mieux connaître le Groupe, ses enjeux, sa culture,Réfléchir à soi / son savoir être / sa posture professionnelle",
            "motivation": "Manager depuis 10 ans, je veux aider à développer le leadership et la connaissance du Groupe."
        },
        {
            "nom": "Bernard", "prenom": "Marc", "sexe": "Homme",
            "tranche_age": "50-55", "ville": "Bordeaux", "region": "Nouvelle-Aquitaine",
            "entite": "SNI", "filiere": "Juridique",
            "anciennete": "20+ ans",
            "attentes_supportees": "Evoluer et gagner en agilité dans un environnement en transformation,Mieux connaître le Groupe, ses enjeux, sa culture",
            "motivation": "Fort de 20 ans d'expérience juridique au sein du groupe, je souhaite partager ma vision stratégique et institutionnelle."
        },
        {
            "nom": "Lefebvre", "prenom": "Claire", "sexe": "Femme",
            "tranche_age": "40-45", "ville": "Paris", "region": "Île-de-France",
            "entite": "CDC", "filiere": "Communication",
            "anciennete": "10-15 ans",
            "attentes_supportees": "Réfléchir à soi / son savoir être / sa posture professionnelle,Mieux connaître le Groupe, ses enjeux, sa culture",
            "motivation": "Experte en communication interne et externe, je veux accompagner des talents dans leur développement personnel et professionnel."
        },
    ]
    data_store['mentores'] = [
        {
            "nom": "Leroy", "prenom": "Emma", "sexe": "Femme",
            "tranche_age": "25-30", "ville": "Paris", "region": "Île-de-France",
            "entite": "Bpifrance", "filiere": "Data",
            "anciennete": "0-5 ans",
            "attentes_categories": "Evoluer et gagner en agilité dans un environnement en transformation,Réfléchir à soi / son savoir être / sa posture professionnelle",
            "attentes_texte": "Je souhaite développer ma posture professionnelle et apprendre à naviguer dans un grand groupe en transformation.",
            "mentor_attendu": ""
        },
        {
            "nom": "Simon", "prenom": "Jade", "sexe": "Femme",
            "tranche_age": "30-35", "ville": "Lyon", "region": "Auvergne-Rhône-Alpes",
            "entite": "CDC Habitat", "filiere": "Finance",
            "anciennete": "5-10 ans",
            "attentes_categories": "Mieux connaître le Groupe, ses enjeux, sa culture",
            "attentes_texte": "Je veux mieux comprendre la stratégie du Groupe et développer mon réseau interne.",
            "mentor_attendu": ""
        },
        {
            "nom": "Moreau", "prenom": "Noah", "sexe": "Homme",
            "tranche_age": "30-35", "ville": "Bordeaux", "region": "Nouvelle-Aquitaine",
            "entite": "Bpifrance", "filiere": "RH",
            "anciennete": "5-10 ans",
            "attentes_categories": "Evoluer et gagner en agilité dans un environnement en transformation,Mieux connaître le Groupe, ses enjeux, sa culture",
            "attentes_texte": "En cours de transition vers un rôle de manager, je cherche un mentor qui a vécu des transformations organisationnelles.",
            "mentor_attendu": ""
        },
        {
            "nom": "Petit", "prenom": "Léa", "sexe": "Femme",
            "tranche_age": "25-30", "ville": "Paris", "region": "Île-de-France",
            "entite": "SNI", "filiere": "Juridique",
            "anciennete": "0-5 ans",
            "attentes_categories": "Réfléchir à soi / son savoir être / sa posture professionnelle",
            "attentes_texte": "Je souhaite travailler sur ma posture et ma légitimité dans un environnement très senior.",
            "mentor_attendu": ""
        },
    ]
    # Réinitialisation complète de l'état des matchs
    data_store['matches'] = []
    data_store['validated'] = []
    data_store['rejected_pairs'] = set()

    return jsonify({"mentors": len(data_store['mentors']), "mentores": len(data_store['mentores'])})


@app.route("/match", methods=["POST"])
def match():
    """
    Calcule les meilleures propositions de matching entre mentors et mentorés disponibles.

    Algorithme en 4 étapes :
        1. Filtrage : on exclut les personnes déjà validées et les paires blacklistées
        2. Scoring : on calcule le score de chaque paire possible via le moteur choisi
        3. Tri : on classe les paires par score décroissant
        4. Greedy : on sélectionne le meilleur match unique pour chaque personne
                    (une personne ne peut pas apparaître dans deux propositions à la fois)

    Corps de la requête JSON :
        mode       : "camembert" | "local" | "online" | "compare"
        api_key    : clé API Mistral (si mode == "online")
        ollama_url : URL Ollama (si mode == "local" ou "compare")
        weights    : pondérations des critères ex: {"attentes": 5, "sexe": 4, ...}
    """
    body = request.json or {}
    mode       = body.get("mode", "camembert")
    api_key    = body.get("api_key", "").strip()
    ollama_url = body.get("ollama_url", "http://localhost:11434")
    # Poids par défaut — adaptés aux critères Fides 10 alter égales
    default_weights = {
        "attentes":    5,  # couverture des besoins du mentoré (critère prioritaire)
        "sexe":        3,  # mixité H/F
        "tranche_age": 4,  # mentor plus âgé
        "filiere":     3,  # complémentarité de filière
        "entite":      2,  # cross-entité
        "anciennete":  4,  # séniorité du mentor
        "region":      3,  # proximité géographique
    }
    weights = body.get("weights", default_weights)

    # Vérification que des données ont bien été chargées
    if not data_store["mentors"] or not data_store["mentores"]:
        return jsonify({"error": "Importe d'abord les données"}), 400

    # --- Étape 1 : Filtrage du pool disponible ---
    # On exclut les personnes dont le match a déjà été validé
    val_mk = {key(v["mentor"])  for v in data_store["validated"]}
    val_ek = {key(v["mentore"]) for v in data_store["validated"]}
    avail_m = [m for m in data_store["mentors"]  if key(m) not in val_mk]
    avail_e = [m for m in data_store["mentores"] if key(m) not in val_ek]

    # On liste toutes les paires possibles en excluant les paires blacklistées (refusées)
    pairs_to_score = []
    for mentor in avail_m:
        for mentore in avail_e:
            pk = (key(mentor), key(mentore))
            if pk not in data_store["rejected_pairs"]:
                pairs_to_score.append((mentor, mentore))

    # Nombre de paires à affiner avec le LLM (configurable via le slider Top N)
    top_n = int(body.get("top_n", 20))

    # Délai entre chaque appel Mistral (configurable selon le plan API)
    # Plan gratuit ≈ 5 req/min → 12s recommandé
    # Plan payant → 1-2s suffisent
    global _mistral_min_delay
    _mistral_min_delay = float(body.get("mistral_delay", 2.0))

    # --- Étape 2a : CamemBERT score TOUTES les paires (rapide, local) ---
    # On commence toujours par CamemBERT pour trier les paires,
    # même en mode Mistral ou Ollama. Cela évite les appels API inutiles.
    all_pairs = []
    for pair in pairs_to_score:
        mentor, mentore = pair
        score, raison = score_camembert(mentor, mentore, weights)
        all_pairs.append({"mentor": mentor, "mentore": mentore,
                           "score": score, "raison": raison, "status": "pending"})

    # Tri par score CamemBERT décroissant pour identifier les meilleures paires
    all_pairs.sort(key=lambda x: x["score"], reverse=True)

    # --- Étape 2b : Affinage LLM sur le TOP N uniquement ---
    # En mode Mistral ou Ollama, on ne passe que les top_n meilleures paires au LLM.
    # Ex: 30×30 = 900 paires → CamemBERT → top 20 → Mistral (20 appels seulement)
    if mode in ("local", "online", "compare"):
        top_pairs = all_pairs[:top_n]  # on ne prend que les meilleures

        def refine_pair(item):
            """Affine le score d'une paire déjà scorée par CamemBERT via le LLM choisi."""
            mentor, mentore = item["mentor"], item["mentore"]
            if mode == "compare":
                # Mode comparaison : on garde CamemBERT ET on ajoute Ollama
                ollama_score, ollama_raison = score_ollama(mentor, mentore, weights, ollama_url)
                item["score_ollama"]  = ollama_score
                item["raison_ollama"] = ollama_raison
            elif mode == "local":
                # Remplacement du score CamemBERT par le score Ollama
                item["score"], item["raison"] = score_ollama(mentor, mentore, weights, ollama_url)
            elif mode == "online":
                # Remplacement du score CamemBERT par le score Mistral
                item["score"], item["raison"] = score_mistral(mentor, mentore, weights, api_key)
            return item

        # Ollama/Compare en parallèle (4 workers), Mistral séquentiel (évite le rate limit)
        workers = 4 if mode in ("local", "compare") else 1
        refined = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(refine_pair, p): p for p in top_pairs}
            for f in concurrent.futures.as_completed(futures):
                try:
                    refined.append(f.result())
                except Exception as e:
                    print(f"[refine_pair] Erreur: {e}")

        # On remplace les top_n paires par les versions affinées,
        # et on garde le reste (scoré par CamemBERT seulement) tel quel
        all_pairs[:top_n] = refined

    # Re-tri final après affinage (les scores LLM peuvent changer l'ordre)
    all_pairs.sort(key=lambda x: x["score"], reverse=True)

    # --- Étape 3 : Tri par score décroissant ---
    all_pairs.sort(key=lambda x: x["score"], reverse=True)

    # --- Étape 4 : Algorithme greedy (sélection optimale) ---
    # On parcourt les paires triées et on garde chaque paire seulement si
    # ni le mentor ni le mentoré n'a déjà été sélectionné.
    # Cela garantit qu'une personne n'apparaît que dans une seule proposition.
    seen_m, seen_e, best = set(), set(), []
    for pair in all_pairs:
        mk, ek = key(pair["mentor"]), key(pair["mentore"])
        if mk not in seen_m and ek not in seen_e:
            best.append(pair)
            seen_m.add(mk)
            seen_e.add(ek)

    # Sauvegarde des propositions finales dans le store
    data_store["matches"] = best

    return jsonify({"matches": best, **compute_stats()})


@app.route("/validate", methods=["POST"])
def validate():
    """
    Valide un match proposé.
    Le mentor et le mentoré sont retirés du pool disponible (ils ne seront plus rematché).

    Corps JSON : {"index": <int>} — index du match dans data_store["matches"]
    """
    idx = request.json.get("index")
    if idx is None or not (0 <= idx < len(data_store["matches"])):
        return jsonify({"error": "Index invalide"}), 400

    # On retire le match de la liste des propositions et on l'ajoute aux validés
    item = data_store["matches"].pop(idx)
    item["status"] = "validated"
    data_store["validated"].append(item)

    # On retourne les stats mises à jour pour rafraîchir les jauges dans l'interface
    return jsonify({"status": "ok", **compute_stats()})


@app.route("/reject", methods=["POST"])
def reject():
    """
    Refuse un match proposé.
    La paire (mentor, mentoré) est ajoutée à la blacklist : elle ne sera plus reproposée.
    MAIS les deux personnes restent disponibles pour être matchées avec d'autres.

    Corps JSON : {"index": <int>} — index du match dans data_store["matches"]
    """
    idx = request.json.get("index")
    if idx is None or not (0 <= idx < len(data_store["matches"])):
        return jsonify({"error": "Index invalide"}), 400

    item = data_store["matches"].pop(idx)
    # Ajout de la paire à la blacklist pour ne plus la reproposer
    data_store["rejected_pairs"].add((key(item["mentor"]), key(item["mentore"])))

    return jsonify({"status": "ok", **compute_stats()})


@app.route("/stats", methods=["GET"])
def stats():
    """Retourne les statistiques actuelles (utilisé pour rafraîchir les jauges)."""
    return jsonify(compute_stats())


@app.route("/reset", methods=["POST"])
def reset():
    """
    Réinitialise les matchs, validations et la blacklist.
    Les données importées (mentors et mentorés) sont conservées.
    """
    data_store["matches"] = []
    data_store["validated"] = []
    data_store["rejected_pairs"] = set()
    return jsonify({"status": "ok", **compute_stats()})


@app.route("/export", methods=["GET"])
def export():
    """
    Génère et télécharge un fichier Excel contenant tous les matchs validés.
    Le fichier est créé en mémoire (pas de fichier temporaire sur le disque).

    Colonnes exportées : Mentor, Domaine, Ville, Mentoré, Domaine, Ville, Score (%), Raison
    """
    if not data_store["validated"]:
        return jsonify({"error": "Aucun match validé"}), 400

    try:
        # Construction des lignes du tableau Excel — champs Fides 10 alter égales
        rows = [{
            "Mentor":                   f"{v['mentor']['prenom']} {v['mentor']['nom']}",
            "Mentor — Sexe":            v['mentor'].get('sexe', ''),
            "Mentor — Tranche d'âge":   v['mentor'].get('tranche_age', ''),
            "Mentor — Entité":          v['mentor'].get('entite', ''),
            "Mentor — Filière":         v['mentor'].get('filiere', ''),
            "Mentor — Ancienneté":      v['mentor'].get('anciennete', ''),
            "Mentor — Région":          v['mentor'].get('region', ''),
            "Mentor — Peut couvrir":    v['mentor'].get('attentes_supportees', ''),
            "Mentoré":                  f"{v['mentore']['prenom']} {v['mentore']['nom']}",
            "Mentoré — Sexe":           v['mentore'].get('sexe', ''),
            "Mentoré — Tranche d'âge":  v['mentore'].get('tranche_age', ''),
            "Mentoré — Entité":         v['mentore'].get('entite', ''),
            "Mentoré — Filière":        v['mentore'].get('filiere', ''),
            "Mentoré — Ancienneté":     v['mentore'].get('anciennete', ''),
            "Mentoré — Région":         v['mentore'].get('region', ''),
            "Mentoré — Attentes":       v['mentore'].get('attentes_categories', ''),
            "Score (%)":                v['score'],
            "Raison":                   v['raison'],
        } for v in data_store["validated"]]

        df = pd.DataFrame(rows)

        # Création du fichier Excel en mémoire avec openpyxl
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as w:
            df.to_excel(w, sheet_name='Matchs Validés', index=False)
        out.seek(0)  # on revient au début du buffer pour que Flask puisse le lire

        return send_file(
            out,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='matchs_valides.xlsx'
        )
    except Exception as ex:
        return jsonify({"error": str(ex)}), 400


# =============================================================================
# DÉMARRAGE DU SERVEUR
# =============================================================================

if __name__ == "__main__":
    # On précharge le modèle CamemBERT avant d'accepter des requêtes
    # pour que le premier matching ne soit pas pénalisé par le temps de chargement
    print("[MentorMatch] Chargement du modèle CamemBERT...")
    get_st_model()
    print("[MentorMatch] Modèle prêt. Lancement du serveur...")

    # Le port peut être configuré via la variable d'environnement PORT
    # utile pour le déploiement en production (ex: Heroku, Railway, etc.)
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)
