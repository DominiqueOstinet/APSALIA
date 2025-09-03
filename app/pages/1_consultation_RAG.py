# app/pages/1_Consultation_RAG.py
import streamlit as st

st.set_page_config(page_title="Consultation RAG", page_icon="🔍", layout="wide")
st.header("🔍 Consultation RAG")

if not st.session_state.get("rag_system"):
    st.info("🔧 Configurez votre clé API Mistral dans la page d’accueil (sidebar), puis revenez ici.")
    st.stop()

question = st.text_area(
    "Posez votre question sur les besoins clients :",
    placeholder="Ex: Le système permet-il la création de templates ?",
    height=100
)

display_mode = st.selectbox("Mode d'affichage :", ["Standard", "Détaillé avec TOP 3"])

if st.button("🔍 Analyser", type="primary") and question.strip():
    try:
        with st.spinner("Analyse RAG en cours..."):
            result = st.session_state.rag_system.query(question)

        st.markdown("---")
        st.subheader("💡 Réponse :")
        st.write(result["answer"])

        if display_mode == "Standard":
            st.subheader(f"📚 Sources consultées ({len(result['sources_info'])}) :")
            for i, source in enumerate(result["sources_info"], 1):
                chunk_type = " [MÉTIER]" if source.get("chunk_type") == "smart_business" else " [GÉNÉRIQUE]"
                st.write(f"{i}. {source['file']} - {source['sheet']} (lignes {source['lines']}){chunk_type}")

        else:
            st.subheader("📋 TOP 3 - Texte exact des meilleures réponses :")
            top_3_docs = result["source_documents"][:3]
            for i, doc in enumerate(top_3_docs, 1):
                md = doc.get("metadata", {})
                src = f"{md.get('source','?')} - {md.get('sheet_name','?')}"
                lines = f"Lignes {md.get('start_row','?')}-{md.get('end_row','?')}"
                ctype = " [MÉTIER]" if md.get("chunk_type") == "smart_business" else " [GÉNÉRIQUE]"
                with st.expander(f"🥇 Réponse #{i} - {src} ({lines}){ctype}"):
                    st.text(doc.get("content", ""))

            st.subheader(f"📚 Toutes les sources ({len(result['sources_info'])}) :")
            for i, source in enumerate(result["sources_info"], 1):
                star = "⭐" if i <= 3 else "  "
                ctype = " [MÉTIER]" if source.get("chunk_type") == "smart_business" else " [GÉNÉRIQUE]"
                st.write(f"{star}{i}. {source['file']} - {source['sheet']} (lignes {source['lines']}){ctype}")

    except Exception as e:
        st.error(f"Erreur lors de l'analyse: {e}")
