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

```bash
pip install -r requirements.txt
```

---

## Configuration

Créez un fichier `.env` à la racine du projet (ne le committez jamais) :

```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
```

Obtenez une clé gratuite sur [https://console.groq.com](https://console.groq.com) — sans carte bancaire.

---

## Lancer les tests

```bash
python tests/test_prompts.py
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
| code        | moyen | meta-llama/llama-3.3-70b-versatile   |
| resume      | moyen | meta-llama/llama-3.3-70b-versatile   |
| traduction  | petit | meta-llama/llama-3.1-8b-instant      |
| execution   | petit | meta-llama/llama-3.1-8b-instant      |

La matrice est configurable via `mapper/models.yaml`.

---

## Intégration MCP (Claude Desktop, Cursor)

Lancez le serveur MCP :

```bash
python mcp_server/server.py
```

Configurez votre agent MCP avec :

```json
{
  "mcpServers": {
    "llm-router": {
      "command": "python",
      "args": ["<chemin_absolu>/mcp_server/server.py"],
      "env": {
        "GROQ_API_KEY": "gsk_xxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

Outils exposés :
- **`route_prompt`** — recommandation uniquement (mode chatbot/LLM)
- **`execute_prompt`** — classification + exécution (mode agent)
- **`get_log_summary`** — résumé agrégé des tokens et coûts

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
