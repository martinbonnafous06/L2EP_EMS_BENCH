# Guide de Déploiement Docker pour Raspberry Pi

Ce guide explique comment installer Docker sur Raspberry Pi OS et déployer le nœud P2P.

## 1. Installation de Docker sur le Raspberry Pi

Ouvrez un terminal sur votre Raspberry Pi et exécutez les commandes suivantes :

```bash
# Mise à jour du système
sudo apt update && sudo apt upgrade -y

# Installation via le script officiel
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Ajouter votre utilisateur au groupe docker (évite d'utiliser sudo à chaque fois)
# Après cette commande, redémarrez votre session ou le Pi.
sudo usermod -aG docker $USER
```

## 2. Préparation du projet

Clonez le dépôt sur chaque Raspberry Pi :
```bash
git clone https://github.com/martinbonnafous06/L2EP_EMS_BENCH.git
cd L2EP_EMS_BENCH
```

## 3. Déploiement du Nœud P2P

### Étape A : Construire l'image
```bash
docker compose build
```

### Étape B : Découverte des pairs
Avant de lancer le nœud, scannez le réseau pour trouver les autres Pi (assurez-vous qu'au moins un autre nœud tourne ou que le port 5555 est ouvert sur les cibles).
```bash
docker compose run --rm node python network_discovery.py
```
Cela créera ou mettra à jour le fichier `peers.json`.

### Étape C : Lancer le nœud
Lancez le nœud en arrière-plan en lui donnant un nom unique :
```bash
export NODE_ID="Pi5_Alpha"
docker compose up -d
```

## 4. Commandes utiles

- **Voir ce qu'il se passe (Logs) :**
  ```bash
  docker compose logs -f
  ```

- **Arrêter le nœud :**
  ```bash
  docker compose down
  ```

- **Mettre à jour le code :**
  ```bash
  git pull
  docker compose build
  docker compose up -d
  ```

## 5. Pourquoi `network_mode: host` ?
Dans ce projet, nous utilisons le mode réseau "host". Cela permet au conteneur d'utiliser directement la carte réseau du Raspberry Pi. C'est indispensable pour :
1. Que `network_discovery.py` puisse scanner votre switch Ethernet.
2. Que les autres nœuds puissent contacter votre Pi sur son adresse IP réelle sans redirection de port complexe.
