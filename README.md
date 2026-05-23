# LLM Router — POC v0.1

Outil de routage intelligent : analyse chaque prompt et le dirige vers le modèle Groq le plus adapté à sa nature, optimisant la consommation de tokens sans sacrifier la qualité.

---

## Structure du projet

```
llm_router/
├── classifier/
│   └── classifier.py        # Appel GPT-OSS 120B via Groq, chain-of-thought, parsing JSON
├── mapper/
│   ├── model_mapper.py      # Résolution catégorie → tier → modèle
│   └── models.yaml          # Matrice de mapping (modifiable sans toucher au code)
├── mcp_server/
│   └── server.py            # Serveur MCP : outils route_prompt / execute_prompt / get_log_summary
├── tests/
│   └── test_prompts.py      # 12 cas de test couvrant toutes les catégories et les deux modes
├── logs/
│   └── router_calls.jsonl   # Log structuré de chaque appel LLM (auto-généré)
├── router.py                # Orchestrateur principal (modes recommendation et execution)
├── logger.py                # Logging token/coût/latence par appel
├── requirements.txt
└── README.md
```

---

## Installation

Installez [uv](https://docs.astral.sh/uv/) si ce n'est pas déjà fait :

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

Puis installez les dépendances :

```bash
uv sync
```

---

## Configuration

Créez un fichier `.env` à la racine du projet (ne le committez jamais) :

```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
PYTHONUTF8=1
```

Obtenez une clé gratuite sur [https://console.groq.com](https://console.groq.com) — sans carte bancaire.

---

## Lancer les tests

```bash
uv run --env-file .env python tests/test_prompts.py
```

Le fichier de test couvre :
- Les 5 catégories unitaires (réflexion, code, résumé, traduction, exécution)
- Les requêtes mixtes avec décomposition en sous-tâches
- Les deux modes : `recommendation` et `execution`
- Des prompts en français, anglais et espagnol
- Un résumé des tokens consommés et coûts à la fin

---

## Pipeline de traitement

```
Prompt utilisateur
       │
       ▼
  [Classifieur]  ←  GPT-OSS 120B (Groq) + chain-of-thought
       │
       ▼  JSON : liste de sous-tâches {tache, categorie, tier}
       │
  [Mapper]  ←  models.yaml
       │
       ▼  modèle Groq résolu par sous-tâche
       │
  ┌────┴────────────────────┐
  │ Mode recommendation     │  → retourne le plan JSON
  │ Mode execution          │  → appelle chaque modèle + retourne les réponses
  └─────────────────────────┘
       │
  [Logger]  →  logs/router_calls.jsonl
```

---

## Catégories de tâches

| Catégorie   | Tier  | Modèle Groq                          |
|-------------|-------|--------------------------------------|
| reflexion   | gros  | openai/gpt-oss-120b                  |
| code        | moyen | llama-3.3-70b-versatile              |
| resume      | moyen | llama-3.3-70b-versatile              |
| traduction  | petit | llama-3.1-8b-instant                 |
| execution   | petit | llama-3.1-8b-instant                 |

La matrice est configurable via `mapper/models.yaml`.

---

## Intégration MCP

Le serveur MCP expose trois outils permettant à n'importe quel agent compatible (Claude Code, Claude Desktop, Cursor, etc.) de router ses prompts via LLM Router sans modifier son code.

### Connexion rapide — Claude Code (même machine, mode stdio)

C'est le mode recommandé si vous clonez le repo localement.

**1. Clonez le repo et installez les dépendances :**

```bash
git clone https://github.com/jkalonji/LLM-router.git
cd LLM-router
uv sync
```

**2. Créez votre fichier `.env` à la racine :**

```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
PYTHONUTF8=1
```

Clé gratuite (sans carte) : [https://console.groq.com](https://console.groq.com)

**3. Ouvrez le dossier dans Claude Code :**

```bash
claude .
```

Le fichier `.mcp.json` inclus dans le repo configure le serveur automatiquement — aucune commande à lancer manuellement. Les outils `route_prompt`, `execute_prompt` et `get_log_summary` sont immédiatement disponibles dans Claude Code.

**Vérification :**

```bash
# Dans Claude Code, tapez :
/mcp
# Vous devez voir : llm-router  connected
```

---

### Connexion depuis une autre machine (mode SSE)

Utilisez ce mode si votre agent tourne sur une machine différente de celle qui héberge LLM Router.

**Sur la machine hôte (celle qui fait tourner LLM Router) :**

```bash
uv run --env-file .env python mcp_server/server.py --transport sse --host 0.0.0.0 --port 8000
```

Le serveur écoute sur `http://0.0.0.0:8000/sse`. Vérifiez que le port 8000 est ouvert dans votre pare-feu.

**Sur la machine cliente (votre agent) :**

```bash
claude mcp add --transport sse llm-router http://<IP_HOTE>:8000/sse
```

Ou ajoutez manuellement dans `~/.claude/mcp.json` (global) ou `.mcp.json` (projet) :

```json
{
  "mcpServers": {
    "llm-router": {
      "url": "http://<IP_HOTE>:8000/sse"
    }
  }
}
```

Remplacez `<IP_HOTE>` par l'adresse IP ou le hostname de la machine hôte.

---

### Connexion depuis Claude Desktop ou Cursor

**Claude Desktop** — éditez le fichier de config :

- Windows : `%APPDATA%\Claude\claude_desktop_config.json`
- macOS : `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "llm-router": {
      "command": "uv",
      "args": ["run", "--env-file", ".env", "python", "mcp_server/server.py"],
      "cwd": "/chemin/absolu/vers/LLM-router"
    }
  }
}
```

**Cursor** — créez `.cursor/mcp.json` à la racine de votre projet avec le même contenu.

> Remplacez `cwd` par le chemin absolu vers le dossier cloné.

---

### Outils exposés

| Outil | Mode | Description |
|---|---|---|
| `route_prompt` | recommendation | Classifie le prompt et retourne le plan de routage JSON — n'exécute pas |
| `execute_prompt` | execution | Classifie et exécute chaque sous-tâche sur le modèle Groq optimal, retourne les réponses |
| `get_log_summary` | monitoring | Résumé agrégé des tokens consommés et des coûts estimés |

**Exemple d'utilisation dans Claude Code après connexion :**

```
Utilisez execute_prompt avec le prompt : "Résume ce texte et traduis-le en anglais : ..."
```

Le routeur décompose automatiquement la tâche (résumé → llama-3.3-70b, traduction → llama-3.1-8b) et retourne les deux réponses.

---

## Format des logs

Chaque appel LLM génère une entrée dans `logs/router_calls.jsonl` :

```json
{
  "call_id": "uuid",
  "timestamp": "2026-05-23T10:00:00Z",
  "mode": "execution",
  "step": "inference",
  "category": "traduction",
  "tier": "petit",
  "model": "meta-llama/llama-3.1-8b-instant",
  "prompt_preview": "Traduis ce texte...",
  "tokens": {
    "prompt_tokens": 42,
    "completion_tokens": 18,
    "total_tokens": 60
  },
  "latency_ms": 312,
  "cost_usd": 0.0,
  "subtask_index": 0,
  "subtask_label": "Traduction",
  "error": null
}
```

---

## Limites du free tier Groq

- 30 requêtes/minute
- 14 400 requêtes/jour
- Le fichier de test insère une pause de 2s entre chaque cas pour rester dans les limites.

---

## Hypothèses à valider (section 5.5 de la spec)

| Hypothèse | Comment la valider |
|---|---|
| Un modèle plus grand = meilleure qualité pour les tâches complexes | Comparer les sorties T01 (gros) vs T02 (moyen) sur un même type de tâche |
| GPT-OSS 120B est suffisamment rapide | Lire `latency_ms` dans les logs pour le step `classifier` |
| Coût classifieur < tokens économisés par le routage | Comparer `tokens_by_step.classifier` vs `tokens_by_step.inference` dans `get_log_summary` |
