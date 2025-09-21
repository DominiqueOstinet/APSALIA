# app/streamlit_app.py
import os
from pathlib import Path
import streamlit as st
from rag.elasticsearch_indexer import get_elastic_client, get_index_stats
from rag.rag_system import EQMSRAGSystem
from utils_docs import hide_native_nav, custom_sidebar_nav, sidebar_system_status

# --- Nav & statut (menu uniquement dans le bandeau de gauche) ---
hide_native_nav()
custom_sidebar_nav(active="Accueil")     # <— Accueil (et plus “Consultation RAG”)
sidebar_system_status()

# --- Page config ---
st.set_page_config(page_title="ApsalIA", page_icon="assets/image_apsalia.png", layout="wide")

# --- CSS : fond bleu, carte centrée, header caché, boutons, etc. ---
st.markdown(
    """
    <style>
    /* supprimer le bandeau Streamlit en haut */
    header[data-testid="stHeader"], div[data-testid="stToolbar"]{
      display:none !important; height:0 !important; visibility:hidden !important;
    }

    /* fond bleu foncé + centrage vertical du conteneur principal */
    .stApp{ background:#0e4f7c !important; }
    [data-testid="stAppViewContainer"]{
      min-height:100vh;
      display:flex;
      align-items:center;
      justify-content:center;
      padding-top:0 !important;
      padding-bottom:0 !important;
    }

    /* carte centrale bleu très clair encadrée */
    .block-container{
      margin: auto !important; 
      max-width:1180px;
      background:#f3f9ff; 
      border:2px solid #1b74b8; 
      border-radius:20px;
      box-shadow:0 16px 40px rgba(0,0,0,.12), 0 4px 12px rgba(0,0,0,.06);
      padding:2.2rem 2.4rem;
    }

    /* sidebar un peu bleutée (le menu natif est déjà masqué par utils) */
    section[data-testid="stSidebar"]{
      background:linear-gradient(180deg,#e1efff 0%, #d3e4f7 100%);
      border-right:1px solid rgba(0,0,0,.08);
    }

    /* petites utilitaires */
    .subtle{ color:#5f6b7a; font-size:.95rem; }
    .badge-ok{
      background:#e6f6ee;color:#106a39;border:1px solid #bfead4;
      padding:.24rem .5rem;border-radius:999px;font-size:.75rem;
    }

    /* bouton primaire bleu */
    .stButton > button[kind="primary"]{
      background:#1b74b8; border-color:#1b74b8; color:white;
    }
    .stButton > button[kind="primary"]:hover{
      background:#0e4f7c; border-color:#0e4f7c;
    }

    /* petite carte descriptive */
    .desc-card{
      background:linear-gradient(180deg,#ffffff 0%,#f6fbff 100%);
      border:1px solid rgba(0,0,0,.06); border-radius:16px;
      padding:14px 16px; margin-top:10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Etat global session ---
if "mistral_api_key" not in st.session_state:
    st.session_state.mistral_api_key = None
if "rag_system" not in st.session_state:
    st.session_state.rag_system = None
if "is_auth" not in st.session_state:
    st.session_state.is_auth = False

# --- Layout principal : gauche (logo + description), droite (connexion) ---
col_left, col_right = st.columns([2,1], gap="large")

# ---- Colonne GAUCHE : Logo + bloc de texte descriptif (pas de titre) ----
with col_left:
    img_path = Path(__file__).parent / "assets" / "image_apsalia.png"
    st.image(str(img_path), width=520)  # logo large

    st.markdown(
        """
        <div class="desc-card">
          <p><b>🔍 Consultation RFI/RFP</b> — Posez vos questions, obtenez des réponses sourcées.</p>
          <p><b>📁 Chargement & Indexation</b> — Déposez de nouveaux RFI/RFP documents, choisissez des mots-clés, indexation automatique.</p>
          <p><b>📄 Utilitaire documentaire</b> — Traduire, résumer, comparer deux documents.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

# ---- Colonne DROITE : Connexion (mot de passe uniquement + spinner) ----
with col_right:
    APP_PASSWORD = os.getenv("APP_PASSWORD", "")
    MISTRAL_API_KEY_ENV = os.getenv("MISTRAL_API_KEY", "")

    st.markdown("### 🔐 Connexion")
    st.markdown("<div class='subtle'>Saisissez le <b>mot de passe Apsalys</b>. </div>", unsafe_allow_html=True)
    st.write("")

    if not st.session_state.is_auth:
        with st.container(border=True):
            pwd = st.text_input("Mot de passe de l'application", type="password", placeholder="••••••••", key="pwd_only")

            c1, c2 = st.columns([1, 1])
            # bouton “Se connecter” avec spinner
            if c1.button("Se connecter", type="primary", use_container_width=True, disabled=(pwd == "")):
                with st.spinner("Connexion en cours…"):
                    if not APP_PASSWORD:
                        st.error("⚠️ APP_PASSWORD non défini côté serveur.")
                    elif pwd != APP_PASSWORD:
                        st.error("Mot de passe incorrect.")
                    elif not MISTRAL_API_KEY_ENV:
                        st.error("⚠️ MISTRAL_API_KEY manquante côté serveur (.env).")
                    else:
                        st.session_state.is_auth = True
                        st.session_state.mistral_api_key = MISTRAL_API_KEY_ENV

                        rag = EQMSRAGSystem(MISTRAL_API_KEY_ENV)
                        if hasattr(rag, "setup_rag_chain"):
                            try:
                                rag.setup_rag_chain()
                            except Exception as e:
                                st.error(f"Erreur lors de l’initialisation du RAG : {e}")
                                st.stop()
                        
                        st.session_state.rag_system = rag
                        st.success("✅ Connexion réussie.")
                        st.rerun()

            c2.button("Effacer", use_container_width=True, on_click=lambda: st.session_state.update(
                {"is_auth": False, "mistral_api_key": None, "rag_system": None, "pwd_only": ""}
            ))

    else:
        st.markdown("<span class='badge-ok'>Connecté</span>", unsafe_allow_html=True)
        if st.button("Se déconnecter", use_container_width=False):
            for k in ("is_auth", "mistral_api_key", "rag_system"):
                st.session_state.pop(k, None)
            st.rerun()

# ================== FOOTER ==================
st.write("")
st.markdown("<div class='tiny' style='text-align:center; opacity:.8;'> Apsalys • apsalIA</div>", unsafe_allow_html=True)