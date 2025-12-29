#!/bin/bash
# Script de démarrage pour ElProfessor
# Ce script active l'environnement virtuel et lance l'application

# Obtenir le répertoire du script (où se trouve le projet)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Activer l'environnement virtuel
if [ -f "elprofessor_env/bin/activate" ]; then
    source elprofessor_env/bin/activate
elif command -v uv &> /dev/null; then
    # Si uv est disponible, utiliser uv run (crée l'env si nécessaire)
    echo "⚠️  Environnement virtuel non trouvé, utilisation de uv run"
    # Charger les variables d'environnement depuis .env si présent
    if [ -f ".env" ]; then
        export $(cat .env | grep -v '^#' | xargs)
    fi
    exec uv run python -m elprofessor
else
    echo "❌ Environnement virtuel non trouvé dans: $SCRIPT_DIR/elprofessor_env"
    echo "   Et uv n'est pas disponible. Veuillez créer l'environnement virtuel d'abord."
    exit 1
fi

# Charger les variables d'environnement depuis .env si présent
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Lancer l'application
exec python -m elprofessor

