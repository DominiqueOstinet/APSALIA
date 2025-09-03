# app/pages/3_Utilitaire_Documentaire.py
import streamlit as st
from app.utils_docs import extract_document_content, DOCX_AVAILABLE, PDF_AVAILABLE

st.set_page_config(page_title="Utilitaire documentaire", page_icon="📄", layout="wide")
st.header("📄 Utilitaire Documentaire")
st.markdown("*Interface pour traiter vos documents sans conservation des données*")
st.info("📌 Les documents traités ici ne sont pas sauvegardés et ne sont pas indexés.")

# Vérif dépendances
missing = []
if not DOCX_AVAILABLE: missing.append("python-docx")
if not PDF_AVAILABLE:  missing.append("PyPDF2")
if missing:
    st.warning(f"⚠️ Bibliothèques manquantes: {', '.join(missing)}")
    st.code(f"pip install {' '.join(missing)}")

uploaded = st.file_uploader(
    "Chargez des documents (PDF, DOCX, DOC, TXT)",
    type=['pdf', 'docx', 'doc', 'txt'],
    accept_multiple_files=True,
    help="Traitements ponctuels : traduction, résumé, comparaison"
)

if not uploaded:
    st.stop()

# Filtre fichiers supportés
supported, unsupported = [], []
for f in uploaded:
    ext = f.name.lower().split(".")[-1]
    if ext == "txt":
        supported.append(f)
    elif ext in ["docx", "doc"] and DOCX_AVAILABLE:
        supported.append(f)
    elif ext == "pdf" and PDF_AVAILABLE:
        supported.append(f)
    else:
        unsupported.append((f, ext))

if unsupported:
    st.warning("⚠️ Fichiers non supportés :")
    for f, ext in unsupported:
        reason = "Bibliothèque manquante" if ext in ["docx", "doc", "pdf"] else "Format non supporté"
        st.write(f"- {f.name} (.{ext}) : {reason}")

if not supported:
    st.stop()

op = st.selectbox("Choisissez l'opération :", ["Traduction automatique", "Résumé de document", "Comparaison de versions"])

# Besoin du LLM pour ces ops :
if "rag_system" not in st.session_state or not st.session_state.rag_system:
    st.error("Veuillez configurer votre clé API Mistral sur la page d’accueil (sidebar).")
    st.stop()

# ───────── Traduction ─────────
if op == "Traduction automatique":
    st.subheader("🌐 Traduction Automatique")
    c1, c2 = st.columns(2)
    with c1:
        src = st.selectbox("Langue source:", ["Auto-détection", "Français", "Anglais", "Allemand", "Espagnol", "Italien"])
    with c2:
        tgt = st.selectbox("Langue cible:", ["Français", "Anglais", "Allemand", "Espagnol", "Italien"])

    doc_name = st.selectbox("Document à traduire:", [f.name for f in supported])

    if st.button("🔄 Traduire"):
        sel = next(f for f in supported if f.name == doc_name)
        with st.spinner(f"Traduction de {doc_name}..."):
            content = extract_document_content(sel)
            if content.startswith("[Erreur"):
                st.error(content)
            else:
                limit = 4000
                if len(content) > limit:
                    content = content[:limit] + "...\n[Contenu tronqué]"
                prompt = f"Traduis le texte suivant de {src} vers {tgt}.\n\nTexte :\n{content}\n\nTraduction :"
                out = st.session_state.rag_system.llm.invoke(prompt)
                st.success("✅ Traduction terminée")
                st.text_area("", value=out.content, height=300)
                st.download_button("📥 Télécharger", data=out.content, file_name=f"{doc_name}_traduit_{tgt}.txt", mime="text/plain")

# ───────── Résumé ─────────
elif op == "Résumé de document":
    st.subheader("📋 Résumé de Document")
    c1, c2 = st.columns(2)
    with c1:
        length = st.selectbox("Longueur du résumé:", ["Court (1-2 paragraphes)", "Moyen (3-5 paragraphes)", "Détaillé (6+ paragraphes)"])
    with c2:
        focus = st.selectbox("Focus:", ["Points principaux", "Aspects techniques", "Décisions importantes", "Actions requises"])
    doc_name = st.selectbox("Document à résumer:", [f.name for f in supported])

    if st.button("📝 Générer le résumé"):
        sel = next(f for f in supported if f.name == doc_name)
        with st.spinner(f"Résumé de {doc_name}..."):
            content = extract_document_content(sel)
            if content.startswith("[Erreur"):
                st.error(content)
            else:
                limit = 6000
                if len(content) > limit:
                    content = content[:limit] + "...\n[Contenu tronqué]"
                prompt = f"Fais un résumé {length.lower()} en te concentrant sur {focus.lower()}.\n\nDocument :\n{content}\n\nRésumé :"
                out = st.session_state.rag_system.llm.invoke(prompt)
                st.success("✅ Résumé généré")
                st.markdown(out.content)
                st.download_button("📥 Télécharger", data=out.content, file_name=f"{doc_name}_resume.md", mime="text/markdown")

# ───────── Comparaison ─────────
else:
    st.subheader("🔍 Comparaison de Versions")
    if len(supported) < 2:
        st.warning("⚠️ Charge au moins 2 documents supportés pour comparer.")
        st.stop()

    c1, c2 = st.columns(2)
    with c1:
        older = st.selectbox("Document version 1 (ancienne):", [f.name for f in supported], key="doc1")
    with c2:
        newer = st.selectbox("Document version 2 (nouvelle):", [f.name for f in supported], key="doc2")

    comp_type = st.selectbox("Type de comparaison:", ["Modifications principales", "Ajouts et suppressions", "Changements techniques", "Analyse complète"])

    if older != newer and st.button("🔄 Comparer les versions"):
        d1 = next(f for f in supported if f.name == older)
        d2 = next(f for f in supported if f.name == newer)
        with st.spinner("Comparaison en cours..."):
            c1 = extract_document_content(d1)
            c2 = extract_document_content(d2)
            if c1.startswith("[Erreur") or c2.startswith("[Erreur"):
                st.error("Erreur extraction d'un des documents.")
            else:
                limit = 3000
                if len(c1) > limit: c1 = c1[:limit] + "...\n[Contenu tronqué]"
                if len(c2) > limit: c2 = c2[:limit] + "...\n[Contenu tronqué]"
                prompt = f"""Compare ces deux versions et identifie les {comp_type.lower()}.

VERSION 1 ({older}) :
{c1}

VERSION 2 ({newer}) :
{c2}

Analyse comparative détaillée :
1. Modifications principales
2. Éléments ajoutés
3. Éléments supprimés
4. Impact des changements

Comparaison :"""
                out = st.session_state.rag_system.llm.invoke(prompt)
                st.success("✅ Comparaison terminée")
                st.subheader(f"Comparaison : {older} → {newer}")
                st.markdown(out.content)
                st.download_button("📥 Télécharger", data=out.content, file_name=f"Comparaison_{older}_vs_{newer}.md", mime="text/markdown")
    elif older == newer:
        st.error("⚠️ Sélectionne deux documents différents.")
