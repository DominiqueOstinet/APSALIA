import os
from pathlib import Path
import pandas as pd

from rag.doc_loader import detect_columns, create_smart_chunks_from_detected
from rag.embeddings import get_embedding_model
from rag.elasticsearch_indexer import (
    get_elastic_client,
    create_index_if_not_exists,
    index_documents_bulk,
)

# === 🔧 CONFIGURATION ===
# indexing.py est placé dans /rag (racine du code dans le conteneur)
# et docker-compose monte ./data -> /rag/data
BASE_DIR = Path(__file__).resolve().parent           # /rag
DOCS_DIR = Path(os.getenv("DOCS_DIR", str(BASE_DIR / "data" / "documents_xlsx")))
INDEX_NAME = os.getenv("ELASTICSEARCH_INDEX", "rfi_rag")

# Contrôle de la suppression de l'index (par défaut: False)
REINDEX_DROP = os.getenv("REINDEX_DROP", "false").lower() in {"1", "true", "yes", "y"}


def main() -> None:
    # === 🚀 INITIALISATION (faites ici pour éviter les effets à l'import) ===
    print("🔌 Connexion Elasticsearch…")
    es = get_elastic_client()

    print("🧠 Chargement du modèle d'embeddings…")
    embedding_model = get_embedding_model()

    # === 🧹 GESTION DE L'INDEX ===
    if REINDEX_DROP:
        print(f"🧹 Suppression de l'index existant '{INDEX_NAME}' (REINDEX_DROP=true)…")
        if es.indices.exists(index=INDEX_NAME):
            es.indices.delete(index=INDEX_NAME)
            print(f"   Index '{INDEX_NAME}' supprimé.")
        else:
            print(f"   Index '{INDEX_NAME}' inexistant, rien à supprimer.")
    else:
        print("ℹ️ REINDEX_DROP=false → on ne supprime pas l'index existant.")

    create_index_if_not_exists(es, INDEX_NAME)
    print(f"✅ Index prêt : {INDEX_NAME}")

    # === 📂 CHARGEMENT & PRÉPARATION DES DOCUMENTS ===
    if not DOCS_DIR.exists():
        raise FileNotFoundError(
            f"Dossier de documents introuvable : {DOCS_DIR}\n"
            "Vérifie le montage de volume dans docker-compose (./data -> /rag/data)."
        )

    all_chunks = []
    xlsx_files = list(DOCS_DIR.glob("*.xlsx"))
    if not xlsx_files:
        print(f"⚠️ Aucun fichier .xlsx trouvé dans {DOCS_DIR}")

    for filepath in xlsx_files:
        print(f"\n📄 Fichier : {filepath.name}")
        all_sheets = pd.read_excel(filepath, sheet_name=None, header=None)

        onglets_exploitables = detect_columns(all_sheets, filepath.name)
        for onglet_data in onglets_exploitables:
            chunks = create_smart_chunks_from_detected(onglet_data, filepath.name)
            all_chunks.extend(chunks)

    print(f"\n✅ Total de chunks détectés : {len(all_chunks)}")

    if not all_chunks:
        print("ℹ️ Aucun chunk à indexer. Fin.")
        return

    # === 🧠 EMBEDDINGS ===
    print("🔄 Création des embeddings…")
    vectors = embedding_model.embed_documents([doc.page_content for doc in all_chunks])

    # === 📤 INDEXATION ELASTICSEARCH ===
    print("📦 Indexation dans Elasticsearch…")
    index_documents_bulk(es, all_chunks, vectors, INDEX_NAME)

    print("🎉 Pipeline terminé !")


if __name__ == "__main__":
    main()

