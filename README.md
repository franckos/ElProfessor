# ElProfessor

Application pour Reachy Mini - Projet indépendant.

## 🚀 Démarrage rapide

### 📦 Première installation (une seule fois)

Si c'est la première fois que vous utilisez ce projet, installez les dépendances :

```bash
# 1. Aller dans le dossier du projet
cd /Users/franckmarandet/Documents/WORK/ALFRED/Reachy/ElProfessor

# 2. Créer l'environnement virtuel (si pas déjà fait)
uv venv elprofessor_env

# 3. Activer l'environnement virtuel
source elprofessor_env/bin/activate

# 4. Installer les dépendances
uv pip install -e .
```

**C'est tout !** Une fois fait, vous n'aurez plus besoin de réinstaller (sauf si vous recréez l'environnement virtuel).

**Note importante** : Si votre environnement virtuel a été créé avec `uv`, utilisez `uv pip install` au lieu de `pip install`.

---

### ▶️ Exécuter l'application (à chaque utilisation)

Une fois les dépendances installées, pour exécuter l'application :

```bash
# 1. Aller dans le dossier du projet
cd /Users/franckmarandet/Documents/WORK/ALFRED/Reachy/ElProfessor

# 2. Activer l'environnement virtuel
source elprofessor_env/bin/activate

# 3. Exécuter votre code
python -m elprofessor
```

**C'est tout !** Pas besoin de réinstaller à chaque fois.

## ⚠️ Important

**Connexion réseau requise** : Le terminal intégré de Cursor bloque l'accès réseau. **Vous devez exécuter le script depuis un terminal externe** (Terminal.app, iTerm2, etc.) pour pouvoir vous connecter au robot Reachy Mini.

## 📝 Notes

- L'environnement virtuel est dans le dossier `elprofessor_env`
- Si votre environnement a été créé avec `uv`, utilisez `uv pip install` au lieu de `pip install`
- Ne pas utiliser `uv run` - utilisez simplement `python` après avoir activé l'environnement
- Si vous obtenez une erreur `ModuleNotFoundError`, vérifiez que vous avez bien activé l'environnement et installé les dépendances

## 📦 Installation sur Reachy

Pour installer ElProfessor sur Reachy, vous pouvez créer un package installable :

```bash
# Depuis le dossier du projet, avec l'environnement activé
uv build
```

Le fichier `.whl` généré pourra être installé sur Reachy.

