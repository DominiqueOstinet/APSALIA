APSALIA ������

APSALIA est un utilitaire documentaire basé sur un système RAG (Retrieval-Augmented Generation).
Il permet de charger, indexer et interroger des documents métier (RFI) grâce à Elasticsearch, des modèles d’embeddings, et une interface Streamlit.

✨ Fonctionnalités

��� Consultation RAG : poser des questions et obtenir des réponses augmentées par vos documents.

��� Chargement & Indexation : importer vos fichiers Excel / Word / PDF pour enrichir la base documentaire.

��� Utilitaire documentaire : explorer et tester vos documents.

��� Authentification simple par mot de passe (clé API Mistral cachée côté serveur).

��� Prérequis

Docker
 & Docker Compose

Un compte Mistral
 et une clé API valide

⚙️ Installation

Cloner le dépôt :

git clone https://github.com/DominiqueOstinet/APSALIA.git
cd APSALIA


Créer le fichier .env à la racine (ne jamais le versionner !) :

# Elasticsearch
ELASTIC_PASSWORD=eqms123!

# Mistral (LLM API)
MISTRAL_API_KEY=ta_clef_mistral_tres_longue

# Mot de passe appli (pour les utilisateurs)
APP_PASSWORD=apsalia (modifiable dans .env)


Lancer Elasticsearch & l’application :

docker compose up -d elasticsearch
docker compose up -d app


Indexer vos documents :
Placez vos fichiers dans ./data/documents_xlsx/ puis lancez :

docker compose run --rm indexer python /rag/indexing.py


Accéder à l’interface :
��� http://localhost:8502

���� Développement

Les fichiers Streamlit sont dans app/ et app/pages/
La logique RAG et Elasticsearch est dans rag/
Pour modifier l’UI, éditez les fichiers app/pages/*.py puis cliquez sur Rerun dans Streamlit (pas besoin de rebuild Docker).
Pour ajouter une dépendance Python → modifiez requirements.txt puis rebuild :
docker compose build --no-cache app indexer

��� Structure du projet
APSALIA/
│
├── app/                  # Interface Streamlit
│   ├── streamlit_app.py
│   └── pages/
│       ├── 1_consultation_RAG.py
│       ├── 2_chargement_Documents.py
│       └── 3_utilitaire_documentaire.py
│
├── rag/                  # Scripts RAG et Elasticsearch
│   ├── indexing.py
│   ├── rag_system.py
│   └── embeddings.py
│
├── data/                 # Vos fichiers métier (montés en volume)
│   └── documents_xlsx/
│
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md

��� Sécurité

La clé Mistral API n’est jamais exposée aux utilisateurs.
Les utilisateurs se connectent avec un mot de passe simple (APP_PASSWORD) pour activer le RAG.
Ne poussez jamais votre .env dans Git.

��� Roadmap (améliorations prévues)

 Amélioration de l’UI Streamlit (layout + design)
 Ajout de graphiques d’analyse documentaire
 Déploiement sur serveur / cloud
