# Dockerfile APSALIA — image unique pour app (Streamlit) et indexer
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/rag \
    HF_HOME=/root/.cache/huggingface

# Dépendances système utiles
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git ca-certificates build-essential \
 && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python (on profite du cache)
WORKDIR /opt/app
COPY requirements.txt /opt/app/requirements.txt
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r /opt/app/requirements.txt

# Copier le code (en prod). En dev, tes volumes écraseront ces dossiers.
WORKDIR /
COPY app/ /app/
COPY rag/ /rag/
# (optionnel) si tu as besoin de données dans l'image:
# COPY data/ /data/

# Exposer le port de Streamlit (service "app")
EXPOSE 8502

# Par défaut: lancer l'UI (le service "indexer" écrasera via `command`)
CMD ["streamlit", "run", "/app/streamlit_app.py", "--server.port=8502", "--server.address=0.0.0.0"]



