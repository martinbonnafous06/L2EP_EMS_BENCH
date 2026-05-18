# Utiliser une image Python légère
FROM python:3.11-slim

# Installer les dépendances système (Nmap pour la découverte, iproute2 pour le réseau)
RUN apt-get update && apt-get install -y \
    nmap \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Définir le répertoire de travail
WORKDIR /app

# Copier les dépendances Python et les installer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY p2p_node.py .
COPY network_discovery.py .
COPY main_app.py .

# Commande par défaut (peut être surchargée dans docker-compose)
CMD ["python", "main_app.py"]
