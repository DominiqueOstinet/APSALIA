# app/pages/2_chargement_Documents.py
from __future__ import annotations

import os
import tempfile
from pathlib import Path
import hashlib
import shutil
from typing import List

import streamlit as st
import pandas as pd

# UI / Nav
from utils_docs import (
    hide_native_nav,
    custom_sidebar_nav,
    sidebar_system_status,
    require_login,
)

# ES & RAG
from rag.elasticsearch_indexer import (
    get_elastic_client,
    get_index_stats,
    create_index_if_not_exists,
    index_documents_bulk,
)
from rag.doc_loader import detect_columns, create_smart_chunks_from_detected,KEYWORDS_BESOIN, KEYWORDS_REPONSE

# éviter les KeyError au premier affichage
if "custom_keywords_besoin" not in st.session_state:
    st.session_state.custom_keywords_besoin = []
if "custom_keywords_reponse" not in st.session_state:
    st.session_state.custom_keywords_reponse = []

from rag.embeddings import get_embedding_model      

# --- Connexion Elasticsearch ---
es = get_elastic_client()

# --- Nom d'index (défini par variable d'env ou valeur par défaut) ---
INDEX_NAME = os.getenv("ELASTICSEARCH_INDEX", "rfi_rag")


# --- Embedding model (chargé une fois en session) ---
if "embedding_model" not in st.session_state:
    st.session_state.embedding_model = get_embedding_model()
embedding_model = st.session_state.embedding_model
# ────────────────────────────────────────────────────────────────────────────────
# Page setup & nav
# ────────────────────────────────────────────────────────────────────────────────
hide_native_nav()
custom_sidebar_nav(active="Chargement & Indexation")
sidebar_system_status()
require_login()

st.set_page_config(page_title="Chargement & Indexation — apsalIA", layout="wide")
st.title("📥 Chargement & Indexation")

st.write(
    "Ajoutez vos fichiers **Excel**. Ils seront copiés en natif pour téléchargement ultérieur, "
    "puis **découpés en chunks** et **indexés** dans Elasticsearch."
)

# ────────────────────────────────────────────────────────────────────────────────
# Constantes & helpers
# ────────────────────────────────────────────────────────────────────────────────
INDEX_NAME = os.getenv("ELASTICSEARCH_INDEX", "rfi_rag")
DOCS_DIR = Path(os.getenv("DOCS_DIR", "/data/documents_xlsx"))
DOCS_DIR.mkdir(parents=True, exist_ok=True)
SOURCE_STORE_DIR = Path(os.getenv("SOURCE_STORE_DIR", "/data/source_store"))
SOURCE_STORE_DIR.mkdir(parents=True, exist_ok=True)


def _sha256_file(path_like) -> str:
    p = Path(path_like)
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy_native_and_get_meta(tmp_path: Path, original_name: str) -> tuple[Path, str, str]:
    """
    Copie tmp_path vers SOURCE_STORE_DIR sous la forme <sha>__<basename>
    Retourne: (stored_path, sha, stored_relpath)
    """
    sha = _sha256_file(tmp_path)
    stored_name = f"{sha}__{Path(original_name).name}"
    stored_path = SOURCE_STORE_DIR / stored_name
    if not stored_path.exists():
        stored_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(tmp_path), str(stored_path))
    # chemin relatif (depuis SOURCE_STORE_DIR) utilisé plus tard pour retrouver le natif
    stored_rel = os.path.relpath(str(stored_path), start="/")
    return stored_path, sha, stored_rel


def _enrich_chunks_with_source_metadata(chunks: List, basename: str, sha: str, relpath: str) -> None:
    """
    Traçabilité source alignée avec indexing.py :
    - source_basename / source_sha256 / source_relpath
    - content_sha256  : hash du contenu du chunk
    - obsolete        : False par défaut
    """
    import hashlib

    for doc in chunks:
        md = getattr(doc, "metadata", None)
        if md is None:
            setattr(doc, "metadata", {})
            md = doc.metadata

        try:
            content_sha = hashlib.sha256(
                (doc.page_content or "").encode("utf-8", errors="ignore")
            ).hexdigest()
        except Exception:
            content_sha = None

        md.update({
            "source_basename": basename,
            "source_sha256": sha,
            "source_relpath": relpath,
            "content_sha256": content_sha,
            "obsolete": False,
        })

# ────────────────────────────────────────────────────────────────────────────────
# Upload UI
# ────────────────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([2, 1])

with col1:
    uploaded_files = st.file_uploader(
    "Déposez un ou plusieurs fichiers Excel",
    type=["xlsx", "xls"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("Glissez-déposez vos fichiers Excel ici (ou cliquez pour sélectionner).")
    st.stop()

with col2:
    st.subheader("Configuration des mots-clés")
    # BESOIN
with st.expander("🔍 Mots-clés BESOIN", expanded=False):
    st.write("**Par défaut :**")
    st.write(", ".join(KEYWORDS_BESOIN))
    new_kw_besoin = st.text_input("Ajouter un mot-clé BESOIN:", key="new_besoin")
    if st.button("Ajouter BESOIN", key="add_besoin"):
        if new_kw_besoin and new_kw_besoin.lower() not in [k.lower() for k in KEYWORDS_BESOIN + st.session_state.get("custom_keywords_besoin", [])]:
            st.session_state.custom_keywords_besoin = st.session_state.get("custom_keywords_besoin", []) + [new_kw_besoin.lower()]
            st.success(f"Ajouté: {new_kw_besoin}")
            st.rerun()
    if st.session_state.get("custom_keywords_besoin"):
        st.write("**Personnalisés :**")
        for i, kw in enumerate(st.session_state.custom_keywords_besoin):
            c1, c2 = st.columns([3, 1])
            with c1: st.write(kw)
            with c2:
                if st.button("❌", key=f"del_besoin_{i}"):
                    st.session_state.custom_keywords_besoin.remove(kw)
                    st.rerun()

# RÉPONSE
with st.expander("💬 Mots-clés RÉPONSE", expanded=False):
    st.write("**Par défaut :**")
    st.write(", ".join(KEYWORDS_REPONSE))
    new_kw_rep = st.text_input("Ajouter un mot-clé RÉPONSE:", key="new_reponse")
    if st.button("Ajouter RÉPONSE", key="add_reponse"):
        if new_kw_rep and new_kw_rep.lower() not in [k.lower() for k in KEYWORDS_REPONSE + st.session_state.get("custom_keywords_reponse", [])]:
            st.session_state.custom_keywords_reponse = st.session_state.get("custom_keywords_reponse", []) + [new_kw_rep.lower()]
            st.success(f"Ajouté: {new_kw_rep}")
            st.rerun()
    if st.session_state.get("custom_keywords_reponse"):
        st.write("**Personnalisés :**")
        for i, kw in enumerate(st.session_state.custom_keywords_reponse):
            c1, c2 = st.columns([3, 1])
            with c1: st.write(kw)
            with c2:
                if st.button("❌", key=f"del_reponse_{i}"):
                    st.session_state.custom_keywords_reponse.remove(kw)
                    st.rerun()


# ────────────────────────────────────────────────────────────────────────────────
# Traitement
# ────────────────────────────────────────────────────────────────────────────────
if st.button("🚀 Lancer le chargement & l’indexation", type="primary"):
    # Prépare l’index
    es = get_elastic_client()
    try:
        create_index_if_not_exists(es, INDEX_NAME)
    except Exception as e:
        st.error(f"Erreur lors de la préparation de l'index ES '{INDEX_NAME}' : {e}")
        st.stop()

    total_chunks = 0
    total_files = 0
    errors = 0

    progress = st.progress(0, text="Préparation…")
    nfiles = len(uploaded_files)

    for i, uf in enumerate(uploaded_files, start=1):
        total_files += 1
        progress.progress(int(100 * (i - 1) / nfiles), text=f"Traitement de {uf.name}…")

        # 1) Sauvegarde temporaire
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp.write(uf.getvalue())
                tmp_path = Path(tmp.name)
        except Exception as e:
            errors += 1
            st.error(f"Erreur d’écriture temporaire pour {uf.name} : {e}")
            continue

        # 2) Copie native + meta (sha, relpath)
        try:
            stored_path, sha, rel = _copy_native_and_get_meta(tmp_path, uf.name)
            st.caption(f"📥 Copie native : {stored_path.name}")
        except Exception as e:
            errors += 1
            st.warning(f"Impossible de copier le fichier source natif ({e})")
            stored_path, sha, rel = None, None, None  # on continue, mais sans natif

        file_chunks: List = []

        # 3) Détection des onglets (aligné sur indexing.py)

        
        try:
            # on lit TOUTES les feuilles sans header ; la fonction de détection va trouver la ligne d’en-tête utile
            all_sheets = pd.read_excel(tmp_path, sheet_name=None, header=None)

            # combine défaut + personnalisés depuis l’UI
            kw_besoin  = KEYWORDS_BESOIN  + st.session_state.get("custom_keywords_besoin", [])
            kw_reponse = KEYWORDS_REPONSE + st.session_state.get("custom_keywords_reponse", [])

            # passe les listes à la détection
            onglets = detect_columns(
                all_sheets,
                uf.name,
                keywords_besoin=kw_besoin,
                keywords_reponse=kw_reponse,
    )
        except Exception as e:
            errors += 1
            st.error(f"Erreur analyse Excel '{uf.name}' : {e}")
            continue

        # 4) Chunking "métier" pour chaque onglet détecté
        for onglet_data in onglets:
            try:
                chunks = create_smart_chunks_from_detected(onglet_data, uf.name)
            except Exception as e:
                st.warning(
                    f"Chunking impossible sur '{uf.name}' / onglet '{onglet_data.get('onglet','?')}' : {e}"
                )
                continue

            # 5) Enrichissement des métadonnées source
            if sha and rel:
                _enrich_chunks_with_source_metadata(
                    chunks,
                    basename=Path(uf.name).name,
                    sha=sha,
                    relpath=rel,
                )

            file_chunks.extend(chunks)

        # 6) Indexation ES
        if not file_chunks:
            st.info(f"Aucun chunk utilisable pour '{uf.name}'.")
        else:
            try:
                st.caption(f"🔎 Indexation dans **{INDEX_NAME}** de {len(file_chunks)} chunks…")
                # Embeddings des chunks du fichier
                vectors = embedding_model.embed_documents([d.page_content for d in file_chunks]) 
                # Indexation ES 
                index_documents_bulk(es, file_chunks, vectors, INDEX_NAME)  # NEW
                total_chunks += len(file_chunks)
                st.success(f"✅ {len(file_chunks)} chunks indexés pour '{uf.name}'")
            except Exception as e:
                errors += 1
                st.error(f"Erreur d’indexation ES pour '{uf.name}' : {e}")

        progress.progress(int(100 * i / nfiles), text=f"Terminé {i}/{nfiles}")

    # ───────── Bilan ─────────
    st.markdown("---")
    st.subheader("Bilan")
    st.write(f"**Fichiers traités** : {total_files}")
    st.write(f"**Chunks indexés** : {total_chunks}")
    if errors:
        st.write(f"**Incidents** : {errors}")

    # Statistiques ES (best-effort)
    try:
        stats = get_index_stats()
        docs = stats.get("docs_count") or stats.get("documents_count")
        size_kb = stats.get("store_size_kb") or (
            round((stats.get("store_size_bytes", 0) / 1024), 1) if stats.get("store_size_bytes") else None
        )
        st.info(f"Index **{INDEX_NAME}** — docs: {docs}, taille: {size_kb} KB")
    except Exception:
        pass
