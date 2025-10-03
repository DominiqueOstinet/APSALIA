"""
Module d'indexation Elasticsearch adapté pour Docker
"""

import os
from typing import List, Dict, Any
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from langchain.schema import Document
import urllib3

# Désactiver les warnings SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_elastic_client():
    host = os.getenv("ELASTIC_HOST", "http://elasticsearch:9200")
    user = os.getenv("ELASTIC_USERNAME", "elastic")
    password = os.getenv("ELASTIC_PASSWORD", "")

    es = Elasticsearch(
        hosts=[host],
        http_auth=(user, password),
        timeout=30,
        max_retries=5,
        retry_on_timeout=True
    )

    if not es.ping():
        raise ConnectionError(
            f"Ping Elasticsearch échoué sur {host} avec user '{user}'"
        )
    print(f"✅ Connexion réussie à Elasticsearch: {host}")
    return es

def create_index_if_not_exists(es: Elasticsearch, index_name: str) -> bool:
    """
    Crée l'index avec le mapping approprié s'il n'existe pas
    """
    
    if es.indices.exists(index=index_name):
        print(f"ℹ️ Index '{index_name}' existe déjà")
        return True
    
    # Mapping optimisé pour le RAG eQMS
    mapping = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,  # Pas de réplication en développement
            "analysis": {
                "analyzer": {
                    "french_analyzer": {
                        "tokenizer": "standard",
                        "filter": ["lowercase", "french_stemmer", "stop_french"]
                    }
                },
                "filter": {
                    "french_stemmer": {
                        "type": "stemmer",
                        "language": "french"
                    },
                    "stop_french": {
                        "type": "stop",
                        "stopwords": "_french_"
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "content": {
                    "type": "text",
                    "analyzer": "french_analyzer",
                    "fields": {
                        "keyword": {
                            "type": "keyword",
                            "ignore_above": 256
                        }
                    }
                },
                "embedding": {
                    "type": "dense_vector",
                    "dims": 768,
                    "index": True,
                    "similarity": "cosine"
                },

                # Champs pour gestion d’obsolescence
                "obsolete": {"type": "boolean"},           
                "content_sha256": {"type": "keyword"}, 

                # Métadonnées du document source
                "source": {"type": "keyword"},
                "sheet_name": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "start_row": {"type": "integer"},
                "end_row": {"type": "integer"},
                "chunk_type": {"type": "keyword"},
                "has_content": {"type": "boolean"},
                "source_basename": {"type": "keyword"},
                "source_sha256":   {"type": "keyword"},
                "source_relpath":  {"type": "keyword"},
                
                # Métadonnées métier
                "client_name": {"type": "keyword"},
                "document_date": {"type": "date", "format": "yyyy-MM-dd||epoch_millis"},
                "category": {"type": "keyword"},
                
                # Timestamp de création
                "indexed_at": {"type": "date"},
                "processing_version": {"type": "keyword"}
            }
        }
    }
    
    try:
        response = es.indices.create(index=index_name, body=mapping)
        print(f"✅ Index '{index_name}' créé avec succès")
        return True
    except Exception as e:
        print(f"❌ Erreur création index '{index_name}': {e}")
        return False

def index_documents_bulk(es: Elasticsearch, documents: List[Document], vectors: List[List[float]], index_name: str) -> bool:
    """
    Indexe une liste de documents en mode bulk
    """
    
    if len(documents) != len(vectors):
        raise ValueError(f"Nombre de documents ({len(documents)}) != nombre de vecteurs ({len(vectors)})")
    
    print(f"📤 Indexation bulk de {len(documents)} documents dans '{index_name}'...")
    
    # Préparer les documents pour bulk
    bulk_docs = []
    for i, (doc, vector) in enumerate(zip(documents, vectors)):
        doc_id = doc.metadata.get('chunk_id', f"doc_{i}")
        
        bulk_docs.append({
            '_index': index_name,
            '_id': doc_id,
            '_source': {
                'content': doc.page_content,
                'embedding': vector,
                'obsolete': bool(doc.metadata.get('obsolete', False)),
                **doc.metadata,  # Toutes les métadonnées
                'indexed_at': '2025-01-01T00:00:00Z',
                'processing_version': 'docker-v1.0'
            }
        })
    
    try:
        # Indexation bulk avec chunks plus petits pour Docker
        success, failed = bulk(es, bulk_docs, chunk_size=100, request_timeout=120)
        
        print(f"✅ Indexation bulk terminée:")
        print(f"   Succès: {success}")
        print(f"   Échecs: {len(failed) if failed else 0}")
        
        # Forcer le refresh
        es.indices.refresh(index=index_name)
        
        # Vérifier le nombre de documents
        count_response = es.count(index=index_name)
        print(f"   Total documents dans l'index: {count_response['count']}")
        
        return len(failed) == 0 if failed else True
        
    except Exception as e:
        print(f"❌ Erreur indexation bulk: {e}")
        return False

def search_documents(es: Elasticsearch, query_vector: List[float], index_name: str, size: int = 5) -> List[Dict]:
    """
    Recherche de documents similaires par vecteur
    """
    
    search_body = {
        "size": size,
        "query": {
            "script_score": {
                "query": {
                     "bool": {
                        # Exclure  les obsolètes 
                        "must_not": [{"term": {"obsolete": True}}]
                }
              },
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                    "params": {"query_vector": query_vector}
            }
        }
    },
        "_source": {
            "excludes": ["embedding"]
    }
}
    
    try:
        response = es.search(index=index_name, body=search_body)
        
        results = []
        for hit in response['hits']['hits']:
            results.append({
                'score': hit['_score'],
                'content': hit['_source']['content'],
                'metadata': {k: v for k, v in hit['_source'].items() if k != 'content'}
            })
        
        return results
        
    except Exception as e:
        print(f"❌ Erreur recherche: {e}")
        return []

def get_index_stats(es: Elasticsearch, index_name: str) -> Dict[str, Any]:
    """
    Récupère les statistiques d'un index
    """
    try:
        if not es.indices.exists(index=index_name):
            return {"error": "Index n'existe pas"}
        
        stats = es.indices.stats(index=index_name)
        count = es.count(index=index_name)
        
        return {
            "documents_count": count['count'],
            "store_size_bytes": stats['indices'][index_name]['total']['store']['size_in_bytes'],
            "indexing_total": stats['indices'][index_name]['total']['indexing']['index_total'],
            "search_total": stats['indices'][index_name]['total']['search']['query_total']
        }
    except Exception as e:
        return {"error": str(e)}
    

def set_chunk_obsolete(es: Elasticsearch, index_name: str, chunk_id: str, obsolete: bool = True) -> dict:
    """
    Marque (ou démarque) un chunk comme obsolète via son _id (= chunk_id).
    """
    try:
        resp = es.update(
            index=index_name,
            id=chunk_id,
            body={"doc": {"obsolete": bool(obsolete)}},
            refresh=True
        )
        return resp
    except Exception as e:
        raise RuntimeError(f"Échec set_chunk_obsolete({chunk_id}): {e}")