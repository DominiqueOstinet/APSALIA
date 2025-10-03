# app/utils_docs.py
import os
import io
import tempfile
import streamlit as st

try:
    from docx import Document
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False

try:
    import pypdf
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False


def extract_document_content(uploaded_file) -> str:
    """
    Extrait le contenu textuel d'un fichier uploadé (TXT, DOCX/DOC, PDF).
    Retourne une chaîne avec messages d’erreur en cas de problème.
    """
    file_extension = uploaded_file.name.lower().split('.')[-1]
    file_content = ""

    try:
        if file_extension == "txt":
            file_content = str(uploaded_file.read(), "utf-8")

        elif file_extension in ["docx", "doc"]:
            if not DOCX_AVAILABLE:
                return "[Erreur: Bibliothèque python-docx non installée. pip install python-docx]"
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
            try:
                doc = Document(tmp_path)
                paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
                file_content = "\n\n".join(paragraphs) if paragraphs else "[Document DOCX vide]"
            except Exception as e:
                file_content = f"[Erreur extraction DOCX: {e}]"
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        elif file_extension == "pdf":
            if not PDF_AVAILABLE:
                return "[Erreur: Bibliothèque PyPDF non installée]"
            try:
                reader = pypdf.PdfReader(io.BytesIO(uploaded_file.getvalue()))
                pages = []
                for i, page in enumerate(reader.pages):
                    try:
                        text = page.extract_text() or ""
                        text = text.strip()
                        if text:
                            pages.append(f"[Page {i+1}]\n{text}")
                    except Exception as e:
                        pages.append(f"[Erreur page {i+1}: {e}]")
                file_content = "\n\n".join(pages) if pages else "[PDF vide ou non extractible]"
            except Exception as e:
                file_content = f"[Erreur extraction PDF: {e}]"

        else:
            file_content = f"[Format non supporté: .{file_extension}]"

    except Exception as e:
        file_content = f"[Erreur générale pour {uploaded_file.name}: {e}]"

    return file_content

INDEX_NAME = os.getenv("ELASTICSEARCH_INDEX", "rfi_rag")

def hide_native_nav():
    """Masque la navigation native de Streamlit (liste des pages)."""
    st.markdown("""
    <style>
    /* cache les différentes variantes du menu natif */
    section[data-testid="stSidebar"] [data-testid="stSidebarNav"] { display: none !important; }
    section[data-testid="stSidebar"] nav[aria-label="Pages"]     { display: none !important; }
    /* style sidebar (léger) */
    section[data-testid="stSidebar"] { background: #f3f9ff; }
    .tiny-status { font-size: 12px; line-height: 1.15; color:#334155; }
    .badge-ok    { background:#e6f6ee; border:1px solid #bfead4; padding:0 6px; border-radius:12px; }
    .badge-warn  { background:#fff6e6; border:1px solid #ffe2ad; padding:0 6px; border-radius:12px; }
    </style>
    """, unsafe_allow_html=True)

def custom_sidebar_nav(active: str | None = None):
    """
    Menu déroulant custom dans la sidebar.
    active : le libellé de la page courante pour présélectionner l'option.
    """
    PAGE_MAP = {
        "Accueil": "streamlit_app.py",
        "🔍 Consultation RAG": "pages/1_consultation_RAG.py",
        "📁 Chargement & Indexation": "pages/2_chargement_Documents.py",
        "📊 Analyse utilisateurs": "pages/3_analyse_utilisateurs.py",
        "📄 Utilitaire documentaire": "pages/4_utilitaire_documentaire.py"   
    }
    labels = list(PAGE_MAP.keys())
    default_index = labels.index(active) if active in labels else 0
    with st.sidebar:
        st.markdown("**Choisir une section**")
        choice = st.selectbox("", labels, index=default_index, key="nav_select")
        if st.button("Ouvrir", use_container_width=True, key="nav_open"):
            st.switch_page(PAGE_MAP[choice])

def sidebar_system_status():
    """Petit encart 'Statut système' en bas de la sidebar (très discret)."""
    from rag.elasticsearch_indexer import get_index_stats, get_elastic_client  # import local
    with st.sidebar:
        st.markdown("---")
        st.caption("🧩 Statut système")
        # Récup stats, compatible 2 signatures possibles
        docs, size_kb, ok = "—", "—", False
        try:
            try:
                stats = get_index_stats()  # signature sans arg
                docs = stats.get("docs_count", "—")
                size_kb = round(stats.get("store_size_kb", 0), 1)
                ok = True
            except TypeError:
                es = get_elastic_client()
                stats = get_index_stats(es, INDEX_NAME)  # signature (client, index)
                if "error" not in stats:
                    docs = stats.get("documents_count", "—")
                    size_kb = round(stats.get("store_size_bytes", 0) / 1024, 1)
                    ok = True
        except Exception:
            ok = False
        st.markdown(
            f"""<div class="tiny-status">
            ES : <span class='{"badge-ok" if ok else "badge-warn"}'>{"OK" if ok else "HS"}</span><br>
            Docs : <b>{docs}</b><br>
            Taille (KB) : <b>{size_kb}</b>
            </div>""",
            unsafe_allow_html=True,
        )


def require_login():
    """
    Bloque l'accès si l'utilisateur n'est pas connecté via mot de passe.
    Affiche un lien pour revenir à l'Accueil et se connecter.
    """
    if not st.session_state.get("is_auth"):
        st.warning("🔒 Veuillez vous connecter sur la page Accueil.")
        st.page_link("streamlit_app.py", label="➡️ Retour à l’Accueil pour se connecter")
        st.stop()