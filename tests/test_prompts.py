"""
tests/test_prompts.py
Fichier de test principal du LLM Router POC.

Lance : python tests/test_prompts.py
Nécessite : GROQ_API_KEY dans le fichier .env à la racine du projet.

Couvre :
- Les 5 catégories unitaires (une tâche = une catégorie)
- Les requêtes mixtes (chain-of-thought + décomposition)
- Les deux modes : recommendation et execution
- La robustesse du classifieur (prompts ambigus, multilingues)
- Le résumé de logs final
"""

import json
import os
import sys
import time
from pathlib import Path

# Charger le .env si présent
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

# Ajouter la racine au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from router import Router
from logger import RouterLogger


# ─── Couleurs console ──────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def header(text: str):
    print(f"\n{BOLD}{BLUE}{'─'*60}{RESET}")
    print(f"{BOLD}{BLUE}  {text}{RESET}")
    print(f"{BOLD}{BLUE}{'─'*60}{RESET}")


def ok(label: str, detail: str = ""):
    print(f"  {GREEN}✓{RESET}  {label}" + (f"  →  {detail}" if detail else ""))


def warn(label: str, detail: str = ""):
    print(f"  {YELLOW}⚠{RESET}  {label}" + (f"  →  {detail}" if detail else ""))


def fail(label: str, detail: str = ""):
    print(f"  {RED}✗{RESET}  {label}" + (f"\n     {detail}" if detail else ""))


# ─── Cas de test ───────────────────────────────────────────────────────────────

TEST_CASES = [
    # --- Tâches unitaires ---
    {
        "id": "T01",
        "label": "Réflexion pure (FR)",
        "prompt": "Analyse les implications stratégiques de l'IA générative sur le marché du travail en Europe d'ici 2030.",
        "mode": "recommendation",
        "expected_categories": ["reflexion"],
        "expected_tiers": ["gros"],
    },
    {
        "id": "T02",
        "label": "Code (FR)",
        "prompt": "Écris une fonction Python qui trie une liste de dictionnaires par une clé donnée.",
        "mode": "recommendation",
        "expected_categories": ["code"],
        "expected_tiers": ["moyen"],
    },
    {
        "id": "T03",
        "label": "Résumé (EN)",
        "prompt": "Summarize the key points of a 10-page report on climate change mitigation strategies.",
        "mode": "recommendation",
        "expected_categories": ["resume"],
        "expected_tiers": ["moyen"],
    },
    {
        "id": "T04",
        "label": "Traduction (FR→EN)",
        "prompt": "Traduis ce texte en anglais : 'La liberté est le droit de faire tout ce que les lois permettent.'",
        "mode": "recommendation",
        "expected_categories": ["traduction"],
        "expected_tiers": ["petit"],
    },
    {
        "id": "T05",
        "label": "Exécution simple (FR)",
        "prompt": "Reformate cette liste en JSON : Nom: Alice, Age: 30, Ville: Paris.",
        "mode": "recommendation",
        "expected_categories": ["execution"],
        "expected_tiers": ["petit"],
    },
    # --- Requêtes mixtes ---
    {
        "id": "T06",
        "label": "Mixte : réflexion + code (FR)",
        "prompt": "Réfléchis à l'architecture la plus adaptée pour une API REST haute disponibilité, puis génère le code Python de base avec FastAPI.",
        "mode": "recommendation",
        "expected_categories": ["reflexion", "code"],
        "expected_tiers": ["gros", "moyen"],
    },
    {
        "id": "T07",
        "label": "Mixte : résumé + traduction (EN)",
        "prompt": "Summarize this article about quantum computing, then translate the summary into French.",
        "mode": "recommendation",
        "expected_categories": ["resume", "traduction"],
        "expected_tiers": ["moyen", "petit"],
    },
    {
        "id": "T08",
        "label": "Mixte 3 tâches (FR)",
        "prompt": "Analyse les tendances du marché crypto en 2024, résume les 5 points clés, puis formate-les en tableau Markdown.",
        "mode": "recommendation",
        "expected_categories": ["reflexion", "resume", "execution"],
        "expected_tiers": ["gros", "moyen", "petit"],
    },
    # --- Mode exécution ---
    {
        "id": "T09",
        "label": "Exécution : traduction courte (mode execution)",
        "prompt": "Translate to English: 'Le chat est sur le tapis.'",
        "mode": "execution",
        "expected_categories": ["traduction"],
        "expected_tiers": ["petit"],
    },
    {
        "id": "T10",
        "label": "Exécution : reformatage JSON (mode execution)",
        "prompt": "Convert to JSON: name=Bob, age=25, city=Lyon.",
        "mode": "execution",
        "expected_categories": ["execution"],
        "expected_tiers": ["petit"],
    },
    # --- Robustesse ---
    {
        "id": "T11",
        "label": "Prompt ambigu court (FR)",
        "prompt": "Aide-moi avec Python.",
        "mode": "recommendation",
        "expected_categories": ["code"],
        "expected_tiers": ["moyen"],
    },
    {
        "id": "T12",
        "label": "Prompt multilingue (ES)",
        "prompt": "Traduce al inglés: 'El sol brilla en el cielo azul.'",
        "mode": "recommendation",
        "expected_categories": ["traduction"],
        "expected_tiers": ["petit"],
    },
]


# ─── Runner de tests ───────────────────────────────────────────────────────────

def run_tests():
    router = Router()
    results = {"passed": 0, "failed": 0, "errors": 0}

    for tc in TEST_CASES:
        header(f"{tc['id']} — {tc['label']}")
        print(f"  {YELLOW}Prompt :{RESET} {tc['prompt'][:100]}{'...' if len(tc['prompt']) > 100 else ''}")
        print(f"  {YELLOW}Mode   :{RESET} {tc['mode']}")

        t0 = time.monotonic()
        try:
            result = router.route(tc["prompt"], mode=tc["mode"])
            elapsed = int((time.monotonic() - t0) * 1000)

            # Vérifier les catégories retournées
            returned_categories = [s.categorie for s in result.subtasks]
            returned_tiers = [s.tier for s in result.subtasks]

            categories_ok = set(returned_categories) == set(tc["expected_categories"])
            tiers_ok = set(returned_tiers) == set(tc["expected_tiers"])

            print(f"\n  Sous-tâches détectées ({len(result.subtasks)}) :")
            for st in result.subtasks:
                token_info = ""
                if st.total_tokens is not None:
                    token_info = f" | {st.total_tokens} tokens | {st.latency_ms}ms"
                response_preview = ""
                if st.response:
                    response_preview = f"\n     └─ Réponse : {st.response[:80]}..."
                print(f"     [{st.tier.upper():6}] {st.categorie:12} → {st.model}{token_info}")
                if response_preview:
                    print(response_preview)

            if categories_ok and tiers_ok:
                ok(f"Catégories et tiers corrects", f"{elapsed}ms total")
                results["passed"] += 1
            else:
                if not categories_ok:
                    warn(
                        f"Catégories inattendues",
                        f"attendu={tc['expected_categories']} reçu={returned_categories}",
                    )
                if not tiers_ok:
                    warn(
                        f"Tiers inattendus",
                        f"attendu={tc['expected_tiers']} reçu={returned_tiers}",
                    )
                results["failed"] += 1

        except Exception as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            fail(f"Erreur ({elapsed}ms)", str(e))
            results["errors"] += 1

        # Pause pour respecter le rate limit Groq (30 req/min)
        time.sleep(2)

    # ─── Résumé final ──────────────────────────────────────────────────────────
    header("RÉSUMÉ DES TESTS")
    total = results["passed"] + results["failed"] + results["errors"]
    print(f"  Tests : {total} | {GREEN}Réussis : {results['passed']}{RESET} | {YELLOW}Écarts : {results['failed']}{RESET} | {RED}Erreurs : {results['errors']}{RESET}")

    header("RÉSUMÉ DES TOKENS & COÛTS")
    logger = RouterLogger()
    summary = logger.summarize()
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    print(f"\n  {BOLD}Logs complets :{RESET} {logger.log_file}\n")


if __name__ == "__main__":
    run_tests()
