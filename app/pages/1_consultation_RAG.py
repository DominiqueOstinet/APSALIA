# app/pages/1_consultation_RAG.py
from __future__ import annotations
import os
from pathlib import Path
import streamlit as st
from typing import Optional

from utils_docs import (
    hide_native_nav, custom_sidebar_nav, sidebar_system_status, require_login
)

# --- Bandeau gauche (menu custom) ---
hide_native_nav()
custom_sidebar_nav(active="Consultation RAG")
sidebar_system_status()
require_login()  # accès protégé (mot de passe)

st.set_page_config(page_title="Consultation RAG — apsalIA", layout="wide")
st.title("🔍 Consultation RAG")

# ---------- Helpers ----------
def get_native_file_path(meta: dict) -> Optional[Path]:
    """
    Récupère le chemin vers le fichier natif en essayant plusieurs stratégies :
      1) source_relpath (relatif à SOURCE_STORE_DIR)
      2) <sha256>__<basename>
      3) *__<basename> (si pas de sha)
      4) recherche par basename direct (fallback)
    Retourne None si rien trouvé.
    """
    source_store = Path(os.getenv("SOURCE_STORE_DIR", "/data/source_store"))

    def _exists(p: Path) -> Optional[Path]:
        try:
            return p if p.exists() else None
        except Exception:
            return None

    # 1) Chemin relatif (meilleur cas)
    rel = (
        meta.get("source_relpath")
        or meta.get("relpath")
        or meta.get("source_path")
        or meta.get("native_relpath")
    )
    if rel:
        p = source_store / rel
        found = _exists(p)
        if found:
            return found

    # Extraire basename et sha depuis différentes clés possibles
    basename = (
        meta.get("source_basename")
        or meta.get("basename")
        or (Path(meta.get("source")).name if meta.get("source") else None)
        or (Path(meta.get("file")).name if meta.get("file") else None)
    )
    sha = meta.get("source_sha256") or meta.get("sha256") or meta.get("hash")

    # 2) Forme canonique "<sha>__<basename>"
    if sha and basename:
        p = source_store / f"{sha}__{basename}"
        found = _exists(p)
        if found:
            return found

    # 3) Si on n'a pas de sha : essayer "*__<basename>"
    if basename:
        try:
            matches = list(source_store.glob(f"*__{basename}"))
            if matches:
                return matches[0]
        except Exception:
            pass

    # 4) Dernier recours : chercher le basename directement dans le répertoire racine
    if basename:
        try:
            direct = source_store / basename
            found = _exists(direct)
            if found:
                return found
        except Exception:
            pass

    return None

def render_answer_block(question: str, answer_text: str, hit, idx: int):
    """Affiche un panneau 'Réponse i' : Question + Réponse (sans métadonnées) + bouton de téléchargement."""
    # Récupère le texte du chunk
    if hasattr(hit, "page_content"):
        raw = hit.page_content
        meta = hit.metadata
    elif isinstance(hit, dict):
        raw = hit.get("content", "")
        meta = hit.get("metadata", {}) or {}
    else:
        raw = str(hit)
        meta = {}

    # Supprimer la partie '--- MÉTADONNÉES ---' si elle existe
    if isinstance(raw, str):
        clean_text = raw.split("--- MÉTADONNÉES ---")[0].strip()
    else:
        clean_text = ""

    with st.expander(f"Réponse {idx+1}", expanded=False):
        st.markdown(f"**Question :** {question}")
        st.markdown("**Réponse :**")
        st.write(clean_text if clean_text else "—")

        native_path = get_native_file_path(meta)
        if native_path is not None:
            try:
                data = native_path.read_bytes()
                st.download_button(
                    label="⬇️ Télécharger le fichier source",
                    data=data,
                    file_name=native_path.name,
                    mime="application/octet-stream",
                )
            except Exception as e:
                st.caption(f"Impossible de joindre le fichier source ({e})")
        else:
            st.caption("Fichier source non disponible.")

# ---------- Corps ----------
rag = st.session_state.get("rag_system")
if rag is None:
    st.warning("Le système RAG n’est pas initialisé. Retournez à l’Accueil pour vous connecter.")
    st.page_link("streamlit_app.py", label="➡️ Accueil")
    st.stop()

# Saisie question + bouton
question = st.text_area(
    "Votre question",
    key="user_question",
    placeholder="Ex. : Quelles sont les exigences client sur … ?"
)
launch = st.button("Lancer l’analyse", type="primary")

# Mémoire des derniers résultats
if "last_rag_result" not in st.session_state:
    st.session_state.last_rag_result = None
if "last_question" not in st.session_state:
    st.session_state.last_question = None

if launch:
    if not question or not question.strip():
        st.warning("Saisissez une question.")
        st.stop()

    # Assure que la chaîne est prête
    if getattr(rag, "rag_chain", None) is None and hasattr(rag, "setup_rag_chain"):
        try:
            rag.setup_rag_chain()
        except Exception as e:
            st.error(f"Erreur lors de l’initialisation du RAG : {e}")
            st.stop()

    with st.spinner("Analyse en cours…"):
        try:
            result = rag.query(question)   # dict: {"answer", "source_documents", ...}
        except Exception as e:
            st.error(f"Erreur lors de l’analyse : {e}")
            st.stop()

        if not result or not result.get("source_documents"):
            st.info("Aucun résultat pertinent.")
            st.stop()

        st.session_state.last_question = question
        st.session_state.last_rag_result = result

# Affichage détaillé systématique
result = st.session_state.last_rag_result
if result:
    st.markdown("---")
    st.subheader("💡 Réponse :")
    st.write(result.get("answer", "").strip())

    st.subheader("📋 TOP 3 - Texte exact des meilleures réponses :")
    src_docs = result.get("source_documents") or []
    for i, doc in enumerate(src_docs[:3]):
        render_answer_block(st.session_state.last_question, result.get("answer", ""), doc, i)
