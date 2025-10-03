"""
Système RAG eQMS adapté pour Docker avec prompts sophistiqués du POC
"""

from typing import List, Dict, Any
from pathlib import Path
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_mistralai import ChatMistralAI

from .embeddings import get_embedding_model
from .elasticsearch_indexer import get_elastic_client, search_documents

class EQMSRAGSystem:
    def __init__(self, mistral_api_key: str = None):
        """
        Initialise le système RAG pour les documents eQMS avec prompts 
        """
        self.mistral_api_key = mistral_api_key
        self.es = None
        self.embedding_model = None
        self.llm = None
        self.rag_chain = None
        self.index_name = "rfi_rag"

        # Initialiser les composants
        self._init_components()
        
        # Template de prompt 
        self.prompt = ChatPromptTemplate.from_template("""
Tu es un consultant technique eQMS qui analyse des cahiers des charges clients pour répondre à leurs demandes commerciales.

CONTEXTE:
- Tu analyses des tableaux Excel contenant les besoins fonctionnels et solutions proposées
- Les références (NC-04, GEN-62, etc.) sont des identifiants de besoins clients
- Tu dois aider à répondre aux questions/affirmations clients

TYPES DE DEMANDES CLIENTS À TRAITER:
- Questions: "Est-ce que la solution permet de...?"
- Affirmations: "La solution doit permettre de..."
- Vérifications: "Confirmez que le système..."
- Recherches: "Où trouve-t-on...?"

MÉTHODE DE RÉPONSE:
1. ANALYSE d'abord si l'information existe dans les documents
2. Si OUI:
   - Distingue BESOIN CLIENT vs SOLUTION PROPOSÉE
   - Cite les éléments factuels
3. Si NON: "Cette fonctionnalité n'est pas documentée dans les besoins analysés"
4. Si PARTIEL: Explique ce qui est couvert et ce qui manque

FORMAT DE RÉPONSE:
- Réponse directe et concise.
- Ne produis PAS de liste exhaustive issue des extraits.
- Si plusieurs sources 'incdisent la même chose, synthétise.
- N’inclus pas de section ‘Références’, ‘Sources’, ‘Élément X’ ou d’énumération d’extraits. L’interface affiche déjà les sources séparément.

DOCUMENTS ANALYSÉS:
{context}

DEMANDE CLIENT: {question}

RÉPONSE:""")

    def _init_components(self):
        """Initialise les composants du système"""
        print("Initialisation des composants RAG...")
        
        # Elasticsearch
        self.es = get_elastic_client()
        print("✅ Elasticsearch connecté")
        
        # Embeddings
        self.embedding_model = get_embedding_model()
        print("✅ Embeddings initialisés")
        
        # LLM Mistral
        if self.mistral_api_key:
            self.llm = ChatMistralAI(
                api_key=self.mistral_api_key,
                model="mistral-tiny",
                temperature=0.0,
                max_tokens=500
            )
            print("✅ LLM Mistral initialisé")
        else:
            print("⚠️ Clé API Mistral manquante")

    def setup_rag_chain(self):
        """Configuration de la chaîne RAG"""
        if not self.llm:
            raise ValueError("LLM doit être initialisé avant la chaîne RAG")
        
        print("🔧 Configuration de la chaîne RAG ")

        def format_docs_for_client(docs):
            """Formatage des documents avec focus sur réponse client"""
            if not docs:
                return "Aucun élément pertinent trouvé dans l'analyse des besoins."

            formatted = []
            for i, doc in enumerate(docs, 1):
                #  uniquement le contenu, sans META
                content = (doc.get('content', '') or '').split('--- MÉTADONNÉES ---')[0].strip()
                formatted.append(content)

            return "\n\n" + "="*60 + "\n\n".join(formatted)

        # Fonction de recherche adaptée pour Elasticsearch
        def retrieve_documents(question: str) -> List[Dict]:
            """Récupère les documents pertinents via Elasticsearch"""
            try:
                # Créer l'embedding de la question
                query_vector = self.embedding_model.embed_query(question)
                
                # Rechercher dans Elasticsearch
                results = search_documents(self.es, query_vector, self.index_name, size=10)
                
                return results
            except Exception as e:
                print(f"Erreur lors de la recherche: {e}")
                return []

        # Chaîne RAG complète avec formatage 
        self.rag_chain = (
            RunnableParallel({
                "context": lambda x: format_docs_for_client(retrieve_documents(x)),
                "question": RunnablePassthrough(),
                "source_documents": lambda x: retrieve_documents(x)
            })
            | RunnableParallel({
                "answer": (lambda x: {"context": x["context"], "question": x["question"]}) | self.prompt | self.llm | StrOutputParser(),
                "source_documents": lambda x: x["source_documents"]
            })
        )

        print("✅ Chaîne RAG configurée ")

    def query(self, question: str) -> Dict[str, Any]:
        """Exécution d'une requête avec formatage """
        if self.rag_chain is None:
            raise ValueError("La chaîne RAG doit être configurée")

        print(f"❓ Question: {question}")
        print("🔍 Analyse en cours...")

        result = self.rag_chain.invoke(question)

        # Formatage des métadonnées des sources
        sources_info = []
        for doc in result["source_documents"]:
            metadata = doc.get("metadata", {})
            source_info = {
                "file": Path(metadata.get('source', 'Unknown')).stem,
                "sheet": metadata.get('sheet_name', 'Unknown'),
                "lines": f"{metadata.get('start_row', '?')}-{metadata.get('end_row', '?')}",
                "has_content": metadata.get('has_content', False),
                "chunk_type": metadata.get('chunk_type', 'unknown'),
                "obsolete": metadata.get('obsolete', False),
                "chunk_id": metadata.get('chunk_id')
            }
            sources_info.append(source_info)

        return {
            "answer": result["answer"],
            "source_documents": result["source_documents"],
            "sources_info": sources_info,
            "sources": list(set([f"{s['file']} - {s['sheet']}" for s in sources_info]))
        }

    def display_result(self, result: Dict[str, Any]):
        """Affichage formaté des résultats (style POC)"""
        print("\n" + "="*80)
        print("💡 RÉPONSE:")
        print("="*80)
        print(result["answer"])

        print(f"\n📚 SOURCES CONSULTÉES ({len(result['sources_info'])}):")
        print("-"*60)
        for i, source in enumerate(result['sources_info'], 1):
            chunk_type_indicator = " [MÉTIER]" if source.get('chunk_type') == 'smart_business' else " [GÉNÉRIQUE]"
            print(f"{i}. {source['file']} - {source['sheet']} (lignes {source['lines']}){chunk_type_indicator}")
        print("="*80)

    def display_result_with_top5(self, result: Dict[str, Any]):
        """Affichage avec TOP 5 des meilleures réponses """
        print("\n" + "="*80)
        print("💡 RÉPONSE:")
        print("="*80)
        print(result["answer"])

        # TOP 5 - Texte exact des meilleures réponses
        print(f"\n📋 TOP 5 - TEXTE EXACT DES MEILLEURES RÉPONSES:")
        print("="*80)

        top_5_docs = result["source_documents"][:5]
        for i, doc in enumerate(top_5_docs, 1):
            metadata = doc.get("metadata", {})
            source_info = f"{Path(metadata.get('source', 'Unknown')).stem} - {metadata.get('sheet_name', 'Unknown')}"
            lines_info = f"Lignes {metadata.get('start_row', '?')}-{metadata.get('end_row', '?')}"
            chunk_type = " [MÉTIER]" if metadata.get('chunk_type') == 'smart_business' else " [GÉNÉRIQUE]"

            print(f"\n🥇 RÉPONSE #{i} - {source_info} ({lines_info}){chunk_type}")
            print("-" * 60)
            print(doc.get('content', ''))

            if i < len(top_5_docs):
                print("\n" + "."*60)

        # Toutes les sources
        print(f"\n📚 TOUTES LES SOURCES CONSULTÉES ({len(result['sources_info'])}):")
        print("-"*60)
        for i, source in enumerate(result['sources_info'], 1):
            chunk_type_indicator = " [MÉTIER]" if source.get('chunk_type') == 'smart_business' else " [GÉNÉRIQUE]"
            star = "⭐" if i <= 5 else "  "
            print(f"{star}{i}. {source['file']} - {source['sheet']} (lignes {source['lines']}){chunk_type_indicator}")
        print("="*80)
