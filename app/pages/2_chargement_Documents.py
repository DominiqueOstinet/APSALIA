# app/pages/2_Chargement_de_Documents.py
import os
import tempfile
import pandas as pd
import streamlit as st

from rag.doc_loader import detect_columns, create_smart_chunks_from_detected, KEYWORDS_BESOIN, KEYWORDS_REPONSE
from rag.embeddings import get_embedding_model
from rag.elasticsearch_indexer import get_elastic_client, index_documents_bulk

INDEX_NAME = os.getenv("ELASTICSEARCH_INDEX", "rfi_rag")

st.set_page_config(page_title="Chargement & Indexation", page_icon="📁", layout="wide")
st.header("📁 Chargement et Indexation de Nouveaux Documents")

col1, col2 = st.columns([2, 1])

with col1:
    uploaded_files = st.file_uploader(
        "Choisissez vos fichiers Excel (.xlsx, .xls)",
        type=['xlsx', 'xls'],
        accept_multiple_files=True,
        help="Sélectionnez un ou plusieurs fichiers Excel contenant vos questionnaires clients"
    )

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

# Traitement
if uploaded_files:
    st.markdown("---")
    st.subheader("Analyse des fichiers")

    if st.button("📤 Analyser et Indexer", type="primary"):
        try:
            # Combiner mots-clés
            all_kw_besoin = KEYWORDS_BESOIN + st.session_state.get("custom_keywords_besoin", [])
            all_kw_rep = KEYWORDS_REPONSE + st.session_state.get("custom_keywords_reponse", [])

            import rag.doc_loader as doc_loader_module
            original_besoin = doc_loader_module.KEYWORDS_BESOIN
            original_reponse = doc_loader_module.KEYWORDS_REPONSE
            doc_loader_module.KEYWORDS_BESOIN = all_kw_besoin
            doc_loader_module.KEYWORDS_REPONSE = all_kw_rep

            all_documents = []
            progress = st.progress(0)
            status = st.empty()

            for i, uf in enumerate(uploaded_files):
                status.text(f"Traitement: {uf.name}")
                progress.progress(i / max(len(uploaded_files), 1))

                # Sauvegarde temporaire
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                    tmp.write(uf.getvalue())
                    tmp_path = tmp.name

                try:
                    all_sheets = pd.read_excel(tmp_path, sheet_name=None, header=None)
                    onglets = detect_columns(all_sheets, uf.name)

                    if onglets:
                        st.success(f"✅ {uf.name}: {len(onglets)} onglet(s) exploitable(s)")
                        for onglet_data in onglets:
                            st.write(f"  📋 {onglet_data['onglet']}")
                            st.write(f"    - Besoin détecté: '{onglet_data['besoin']['contenu']}'")
                            st.write(f"    - {len(onglet_data['reponses'])} colonne(s) de réponse")
                            chunks = create_smart_chunks_from_detected(onglet_data, uf.name)
                            all_documents.extend(chunks)
                    else:
                        st.warning(f"⚠️ {uf.name}: Aucun onglet exploitable trouvé")
                finally:
                    os.unlink(tmp_path)

            progress.progress(1.0)
            status.text("Analyse terminée")

            # Restaurer mots-clés
            doc_loader_module.KEYWORDS_BESOIN = original_besoin
            doc_loader_module.KEYWORDS_REPONSE = original_reponse

            if all_documents:
                st.success(f"📊 Total: {len(all_documents)} chunks créés")

                with st.spinner("Création des embeddings et indexation..."):
                    model = get_embedding_model()
                    vectors = model.embed_documents([doc.page_content for doc in all_documents])

                    es = get_elastic_client()
                    success = index_documents_bulk(es, all_documents, vectors, INDEX_NAME)

                    if success:
                        st.success("✅ Documents indexés avec succès!")
                        st.balloons()
                    else:
                        st.error("❌ Erreur lors de l'indexation")
            else:
                st.error("❌ Aucun document exploitable trouvé dans les fichiers")

        except Exception as e:
            st.error(f"Erreur lors du traitement: {e}")
            if 'doc_loader_module' in locals():
                doc_loader_module.KEYWORDS_BESOIN = original_besoin
                doc_loader_module.KEYWORDS_REPONSE = original_reponse

# Aperçu rapide
if uploaded_files:
    st.markdown("---")
    st.subheader("Aperçu des fichiers chargés")
    for uf in uploaded_files:
        with st.expander(f"📄 {uf.name} ({uf.size} bytes)"):
            try:
                sheets_info = pd.read_excel(uf, sheet_name=None, header=None, nrows=0)
                st.write(f"**Onglets détectés:** {list(sheets_info.keys())}")
                first_sheet = list(sheets_info.keys())[0]
                sample = pd.read_excel(uf, sheet_name=first_sheet, nrows=5)
                st.write(f"**Aperçu de '{first_sheet}':**")
                st.dataframe(sample)
            except Exception as e:
                st.error(f"Erreur lecture aperçu: {e}")
