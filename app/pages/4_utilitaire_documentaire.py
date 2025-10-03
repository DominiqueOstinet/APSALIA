# app/pages/3_Utilitaire_Documentaire.py
import streamlit as st
from app.utils_docs import extract_document_content, DOCX_AVAILABLE, PDF_AVAILABLE

from utils_docs import hide_native_nav, custom_sidebar_nav, sidebar_system_status, require_login

hide_native_nav()
custom_sidebar_nav(active="Consultation RAG")  # ou la page courante
sidebar_system_status()
require_login()  # ⬅️ empêche l'accès si non connecté

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

    # Choix de la longueur uniquement
    length = st.selectbox(
        "Longueur du résumé :",
        ["Court (1-2 paragraphes)", "Moyen (3-5 paragraphes)", "Détaillé (6+ paragraphes)"]
    )

    # Choix du document
    doc_name = st.selectbox("Document à résumer :", [f.name for f in supported])

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

                # Nouveau prompt sans notion de "focus"
                prompt = f"Fais un résumé {length.lower()} du document suivant :\n\n{content}\n\nRésumé :"

                out = st.session_state.rag_system.llm.invoke(prompt)
                st.success("✅ Résumé généré")
                st.markdown(out.content)
                st.download_button(
                    "📥 Télécharger",
                    data=out.content,
                    file_name=f"{doc_name}_resume.md",
                    mime="text/markdown"
                )

# ───────── Comparaison ─────────
else:
    st.subheader("🔍 Comparaison de Versions")
    if len(supported) < 2:
        st.warning("⚠️ Charge au moins 2 documents supportés pour comparer.")
        st.stop()

    c1_col, c2_col = st.columns(2)
    with c1_col:
        older = st.selectbox("Document version 1 (ancienne) :", [f.name for f in supported], key="doc1")
    with c2_col:
        newer = st.selectbox("Document version 2 (nouvelle) :", [f.name for f in supported], key="doc2")

    if older == newer:
        st.error("⚠️ Sélectionne deux documents différents.")
    elif st.button("🔄 Comparer les versions"):
        d1 = next(f for f in supported if f.name == older)
        d2 = next(f for f in supported if f.name == newer)

        import re, difflib
        from typing import List, Tuple

        def split_units(txt: str) -> List[str]:
            """Découpe le texte en unités lisibles (phrases / puces / lignes)."""
            t = re.sub(r"[•\-\u2022]\s*", "\n", txt)  # puces → retours ligne
            parts = re.split(r"(?<=[\.\!\?])\s+|\n+", t)  # fin de phrase OU newline
            return [p.strip() for p in parts if p and p.strip()]

        def word_diff(a: str, b: str) -> str:
            """Diff mot-à-mot : '2021 → 1999, haut → très haut, …'"""
            a_w, b_w = a.split(), b.split()
            diff = list(difflib.ndiff(a_w, b_w))
            changes, i = [], 0
            while i < len(diff):
                if diff[i].startswith("- ") and i+1 < len(diff) and diff[i+1].startswith("+ "):
                    changes.append(f"{diff[i][2:]} → {diff[i+1][2:]}")
                    i += 2
                elif diff[i].startswith("- "):
                    changes.append(f"supprimé: {diff[i][2:]}")
                    i += 1
                elif diff[i].startswith("+ "):
                    changes.append(f"ajouté: {diff[i][2:]}")
                    i += 1
                else:
                    i += 1
            return ", ".join(changes)

        with st.spinner("Comparaison en cours..."):
            text_old = extract_document_content(d1)
            text_new = extract_document_content(d2)

            if text_old.startswith("[Erreur") or text_new.startswith("[Erreur"):
                st.error("Erreur d'extraction d'un des documents.")
                st.stop()

            # Tronquage sécurité
            limit = 20000
            if len(text_old) > limit: text_old = text_old[:limit]
            if len(text_new) > limit: text_new = text_new[:limit]

            old_units = split_units(text_old)
            new_units = split_units(text_new)

            # Aligne les unités (phrases/lignes) entre anciennes et nouvelles versions
            sm = difflib.SequenceMatcher(None, old_units, new_units)
            added: List[str] = []
            removed: List[str] = []
            modified: List[Tuple[str, str, str]] = []  # (ancien, nouveau, diff)

            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    continue
                elif tag == "delete":
                    removed.extend(old_units[i1:i2])
                elif tag == "insert":
                    added.extend(new_units[j1:j2])
                elif tag == "replace":
                    # On associe les paires dans la zone remplacée
                    a_block = old_units[i1:i2]
                    b_block = new_units[j1:j2]
                    n = min(len(a_block), len(b_block))
                    for k in range(n):
                        a_sent, b_sent = a_block[k], b_block[k]
                        diff_words = word_diff(a_sent, b_sent)
                        if a_sent != b_sent:
                            modified.append((a_sent, b_sent, diff_words))
                    # S'il reste des lignes en plus d'un côté, ce sont des ajouts/suppressions purs
                    if len(a_block) > n:
                        removed.extend(a_block[n:])
                    if len(b_block) > n:
                        added.extend(b_block[n:])

            # ----- Rendu -----
            st.success("✅ Comparaison terminée")
            st.subheader(f"Comparaison : {older} → {newer}")

            st.markdown("### Éléments ajoutés")
            if added:
                for u in added:
                    st.markdown(f"- {u}")
            else:
                st.markdown("_Aucun_")

            st.markdown("### Éléments supprimés")
            if removed:
                for u in removed:
                    st.markdown(f"- {u}")
            else:
                st.markdown("_Aucun_")

            st.markdown("### Éléments modifiés")
            if modified:
                for old_s, new_s, d in modified:
                    st.markdown(f"- **Ancienne :** {old_s}\n  **Nouvelle :** {new_s}\n  ↳ **Différences :** {d if d else 'modifications mineures'}")
            else:
                st.markdown("_Aucun_")

            # ----- Export Markdown -----
            md_lines = []
            md_lines.append(f"# Comparaison : {older} → {newer}")
            md_lines.append("")
            md_lines.append("## Éléments ajoutés")
            if added:
                md_lines.extend([f"- {u}" for u in added])
            else:
                md_lines.append("_Aucun_")
            md_lines.append("")
            md_lines.append("## Éléments supprimés")
            if removed:
                md_lines.extend([f"- {u}" for u in removed])
            else:
                md_lines.append("_Aucun_")
            md_lines.append("")
            md_lines.append("## Éléments modifiés")
            if modified:
                for old_s, new_s, d in modified:
                    md_lines.append(f"- **Ancienne :** {old_s}")
                    md_lines.append(f"  **Nouvelle :** {new_s}")
                    md_lines.append(f"  ↳ **Différences :** {d if d else 'modifications mineures'}")
            else:
                md_lines.append("_Aucun_")
            md_lines.append("")

            md_text = "\n".join(md_lines)
            st.download_button(
                "📥 Télécharger",
                data=md_text,
                file_name=f"Comparaison_{older}_vs_{newer}.md",
                mime="text/markdown"
            )