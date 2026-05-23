# LLM Router — Guide agent

## Ce que fait ce projet

LLM Router analyse chaque prompt et le dirige vers le modèle Groq le plus adapté à sa complexité, via le protocole MCP. Objectif : réduire les coûts d'inférence sans sacrifier la qualité.

Deux modes :
- `recommendation` — classifie et retourne un plan JSON (quel modèle pour quelle sous-tâche)
- `execution` — classifie et exécute chaque sous-tâche sur le bon modèle Groq, retourne les réponses

## Prérequis

- [uv](https://docs.astral.sh/uv/) installé (`uv --version` pour vérifier)
- Une clé API Groq gratuite : https://console.groq.com

## Setup complet (à exécuter une seule fois)

```bash
# 1. Installer uv si absent
# Windows :
irm https://astral.sh/uv/install.ps1 | iex
# macOS / Linux :
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Installer les dépendances
uv sync

# 3. Créer le fichier d'environnement
# Remplace gsk_xxx par ta clé Groq réelle
echo "GROQ_API_KEY=gsk_xxx" > .env
echo "PYTHONUTF8=1" >> .env
```

## Vérification rapide

```bash
# Lance la suite de tests complète (12 cas, ~30s)
uv run --env-file .env python tests/test_prompts.py
```

Résultat attendu : `Tests : 12 | Réussis : 12 | Écarts : 0 | Erreurs : 0`

## Connexion MCP

### Depuis Claude Code sur la même machine (stdio)

Le fichier `.mcp.json` à la racine configure automatiquement le serveur MCP.
**Aucune commande à lancer manuellement** — Claude Code démarre le serveur à la demande.

### Depuis un agent sur une autre machine (SSE)

**1. Démarrer le serveur en mode SSE sur la machine hôte :**

```bash
uv run --env-file .env python mcp_server/server.py --transport sse --host 0.0.0.0 --port 8000
```

Le serveur écoute sur `http://0.0.0.0:8000/sse`. Tu peux changer le port avec `--port`.

**2. Connecter l'agent distant :**

Dans Claude Code (machine distante), ajouter le serveur via la commande :

```bash
claude mcp add --transport sse llm-router http://<IP_HOTE>:8000/sse
```

Ou dans le fichier `~/.claude/mcp.json` (ou `.mcp.json` du projet) :

```json
{
  "mcpServers": {
    "llm-router": {
      "url": "http://<IP_HOTE>:8000/sse"
    }
  }
}
```

Remplace `<IP_HOTE>` par l'IP ou le hostname de la machine qui fait tourner le serveur.

### Outils disponibles après connexion

| Outil | Usage |
|---|---|
| `route_prompt` | Passe un prompt, reçois le plan de routage JSON |
| `execute_prompt` | Passe un prompt, reçois les réponses exécutées sur les bons modèles |
| `get_log_summary` | Résumé des tokens consommés et coûts estimés |

## Fichiers clés

| Fichier | Rôle |
|---|---|
| `router.py` | Orchestrateur principal |
| `classifier/classifier.py` | Appel GPT-OSS 120B, chain-of-thought, extraction JSON |
| `mapper/models.yaml` | Matrice catégorie → tier → modèle (éditable sans toucher au code) |
| `mcp_server/server.py` | Serveur MCP stdio |
| `logger.py` | Logging JSONL par appel LLM |
| `tests/test_prompts.py` | 12 cas de test |
| `.mcp.json` | Config MCP pour Claude Code |
| `.env` | Secrets locaux (non commité) |

## Commandes utiles

```bash
# Tests
uv run --env-file .env python tests/test_prompts.py

# Serveur MCP local (stdio — diagnostic)
uv run --env-file .env python mcp_server/server.py

# Serveur MCP distant (SSE)
uv run --env-file .env python mcp_server/server.py --transport sse --port 8000

# Appel direct au router en Python
uv run --env-file .env python -c "
from router import Router
r = Router()
result = r.route('Traduis bonjour en anglais', mode='execution')
print(result.to_dict())
"
```

## Limites free tier Groq

- 30 req/min — les tests insèrent une pause de 2s entre chaque cas
- 14 400 req/jour
