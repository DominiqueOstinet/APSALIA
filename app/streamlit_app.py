# app/streamlit_app.py
import os
import streamlit as st
from rag.elasticsearch_indexer import get_elastic_client, get_index_stats
from rag.rag_system import EQMSRAGSystem

INDEX_NAME = os.getenv("ELASTICSEARCH_INDEX", "rfi_rag")

st.set_page_config(page_title="ApsalIA", layout="wide")
st.title("ApsalIA")
st.markdown("---")
st.caption("Votre Assistant intelligent")

# ─────────────────────────────────────────────────────────
# État global
# ─────────────────────────────────────────────────────────
if "mistral_api_key" not in st.session_state:
    st.session_state.mistral_api_key = None
if "rag_system" not in st.session_state:
    st.session_state.rag_system = None

# ─────────────────────────────────────────────────────────
# Statut Elasticsearch / index (petit encart à droite)
# ─────────────────────────────────────────────────────────
col_left, col_right = st.columns([2,1], gap="large")

with col_right:
    st.header("Statut système")
    try:
        es = get_elastic_client()
        st.success("✅ Elasticsearch connecté")
        stats = get_index_stats(es, INDEX_NAME)
        if "error" not in stats:
            st.metric("Docs indexés", stats.get("documents_count", 0))
            st.metric("Taille index (KB)", round(stats.get("store_size_bytes", 0) / 1024, 1))
        else:
            st.error("❌ Index non trouvé")
    except Exception as e:
        st.error(f"❌ Erreur connexion: {e}")

with col_left:
    # ─────────────────────────────────────────────────────────
    # Configuration RAG (formulaire sur la page d'accueil)
    # ─────────────────────────────────────────────────────────
    st.subheader("⚙️ Configuration RAG")

    if st.session_state.rag_system is None:
        with st.form("config_rag"):
            mode = st.radio("Choisissez votre méthode :", ["Mot de passe", "Clé API Mistral"], horizontal=True)
            api_key = None

            if mode == "Mot de passe":
                pwd = st.text_input("Mot de passe de l'application", type="password")
            else:
                api_key = st.text_input("Clé API Mistral (option avancée)", type="password")

            submitted = st.form_submit_button("Configurer")
            if submitted:
                if mode == "Mot de passe":
                    if pwd and pwd == os.getenv("APP_PASSWORD"):
                        api_key = os.getenv("MISTRAL_API_KEY")
                        if not api_key:
                            st.error("La clé Mistral serveur (MISTRAL_API_KEY) est absente. Contactez l’admin.")
                            st.stop()
                        st.session_state.mistral_api_key = api_key
                        st.session_state.rag_system = EQMSRAGSystem(api_key)
                        st.session_state.rag_system.setup_rag_chain()
                        st.success("✅ Système RAG configuré")
                        st.rerun()
                    else:
                        st.error("Mot de passe invalide.")
                else:
                    if api_key:
                        st.session_state.mistral_api_key = api_key
                        st.session_state.rag_system = EQMSRAGSystem(api_key)
                        st.session_state.rag_system.setup_rag_chain()
                        st.success("✅ Système RAG configuré")
                        st.rerun()
                    else:
                        st.error("Veuillez saisir une clé API.")
    else:
        st.success("✅ RAG configuré")
        if st.button("Réinitialiser la configuration"):
            st.session_state.mistral_api_key = None
            st.session_state.rag_system = None
            st.rerun()

    st.markdown("---")
    st.info(
        "Utilisez le menu « Pages » à gauche :\n"
        "• 🔍 Consultation RAG\n"
        "• 📁 Chargement & Indexation\n"
        "• 📄 Utilitaire documentaire"
    )

