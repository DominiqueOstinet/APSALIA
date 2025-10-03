import os
from pathlib import Path
import hashlib
import shutil
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
DOCS_DIR = Path(os.getenv("DOCS_DIR", "/data/documents_xlsx"))
INDEX_NAME = os.getenv("ELASTICSEARCH_INDEX", "rfi_rag")

# Où copier les fichiers sources pour téléchargement ultérieur
SOURCE_STORE_DIR = Path(os.getenv("SOURCE_STORE_DIR", "/data/source_store"))

# Contrôle de la suppression de l'index (par défaut: False)
REINDEX_DROP = os.getenv("REINDEX_DROP", "false").lower() in {"1", "true", "yes", "y"}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _enrich_chunks_with_source_metadata(chunks, file_path: Path, stored_path: Path, sha: str) -> None:
    """
    Ajoute les métadonnées de traçabilité du fichier source sur chaque chunk.
    - source_basename : nom du fichier d'origine
    - source_sha256   : hash du fichier d'origine (anti-duplication/version)
    - source_relpath  : chemin relatif (depuis /) du fichier copié dans SOURCE_STORE_DIR
    - content_sha256  : hash du CONTENU du chunk (pour repérer les doublons/évolutions)
    - obsolete        : drapeau métier (False par défaut)
    """
    import hashlib

    rel_from_root = os.path.relpath(str(stored_path), start="/")
    basename = file_path.name
    for doc in chunks:
        if not hasattr(doc, "metadata") or doc.metadata is None:
            doc.metadata = {}

        # hash du contenu du chunk (chaîne page_content)
        try:
            content_sha = hashlib.sha256(
                (doc.page_content or "").encode("utf-8", errors="ignore")
            ).hexdigest()
        except Exception:
            content_sha = None

        doc.metadata.update({
            "source_basename": basename,
            "source_sha256": sha,
            "source_relpath": rel_from_root,
            "content_sha256": content_sha,
            "obsolete": False,
        })


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

    SOURCE_STORE_DIR.mkdir(parents=True, exist_ok=True)

    all_chunks = []
    xlsx_files = list(DOCS_DIR.glob("*.xlsx"))
    if not xlsx_files:
        print(f"⚠️ Aucun fichier .xlsx trouvé dans {DOCS_DIR}")

    for filepath in xlsx_files:
        print(f"\n📄 Fichier : {filepath.name}")

        # 1) Copie du fichier natif (idempotente) + calcul du SHA
        sha = _sha256_file(filepath)
        stored_name = f"{sha}__{filepath.name}"
        stored_path = SOURCE_STORE_DIR / stored_name
        if not stored_path.exists():
            stored_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(filepath), str(stored_path))
            print(f"📥 Copie du fichier source → {stored_path}")
        else:
            print(f"↪️ Copie déjà présente : {stored_path.name}")

        # 2) Détection de la structure (doc_loader) — si non détectée, on IGNORE le fichier
        try:
            all_sheets = pd.read_excel(filepath, sheet_name=None, header=None)
            onglets_exploitables = detect_columns(all_sheets, filepath.name)
        except Exception as e:
            print(f"❌ Erreur lors de la détection de structure pour {filepath.name} : {e}")
            print("⛔ Fichier ignoré (structure non conforme).")
            continue

        # 3) Chunking métier + enrichissement des métadonnées de traçabilité
        try:
            for onglet_data in onglets_exploitables:
                chunks = create_smart_chunks_from_detected(onglet_data, filepath.name)
                if not chunks:
                    continue
                _enrich_chunks_with_source_metadata(chunks, filepath, stored_path, sha)
                all_chunks.extend(chunks)
        except Exception as e:
            print(f"❌ Erreur lors de la création des chunks pour {filepath.name} : {e}")
            print("⛔ Fichier ignoré (échec du traitement métier).")
            continue

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
