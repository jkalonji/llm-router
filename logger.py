"""
logger.py
Logging structuré de chaque appel LLM : tokens consommés, modèle, tier, latence.
Objectif : traçabilité complète pour calcul de coût et validation des hypothèses POC.
"""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional


LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / "router_calls.jsonl"


@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class RouterLogEntry:
    call_id: str
    timestamp: str
    mode: str                        # "recommendation" | "execution"
    step: str                        # "classifier" | "inference"
    category: Optional[str]          # catégorie identifiée par le classifieur
    tier: Optional[str]              # petit | moyen | gros
    model: str                       # modèle Groq utilisé
    prompt_preview: str              # 120 premiers chars du prompt
    tokens: TokenUsage
    latency_ms: int
    cost_usd: float                  # calculé sur base du YAML (0.0 en free tier)
    subtask_index: Optional[int]     # index si requête mixte décomposée
    subtask_label: Optional[str]     # libellé de la sous-tâche
    error: Optional[str]             # message d'erreur si échec


def _compute_cost(
    prompt_tokens: int,
    completion_tokens: int,
    cost_per_million_input: float,
    cost_per_million_output: float,
) -> float:
    return (
        prompt_tokens / 1_000_000 * cost_per_million_input
        + completion_tokens / 1_000_000 * cost_per_million_output
    )


class RouterLogger:
    def __init__(self, log_file: Path = LOG_FILE):
        self.log_file = log_file

    def log(self, entry: RouterLogEntry) -> None:
        """Appende une entrée au fichier JSONL."""
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def build_entry(
        self,
        *,
        mode: str,
        step: str,
        model: str,
        prompt: str,
        usage,                        # objet usage retourné par Groq SDK
        latency_ms: int,
        cost_per_million_input: float = 0.0,
        cost_per_million_output: float = 0.0,
        category: Optional[str] = None,
        tier: Optional[str] = None,
        subtask_index: Optional[int] = None,
        subtask_label: Optional[str] = None,
        error: Optional[str] = None,
    ) -> RouterLogEntry:
        tokens = TokenUsage(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        )
        return RouterLogEntry(
            call_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            mode=mode,
            step=step,
            category=category,
            tier=tier,
            model=model,
            prompt_preview=prompt[:120],
            tokens=tokens,
            latency_ms=latency_ms,
            cost_usd=_compute_cost(
                tokens.prompt_tokens,
                tokens.completion_tokens,
                cost_per_million_input,
                cost_per_million_output,
            ),
            subtask_index=subtask_index,
            subtask_label=subtask_label,
            error=error,
        )

    def summarize(self) -> dict:
        """Lit le fichier JSONL et retourne un résumé agrégé des coûts et tokens."""
        if not self.log_file.exists():
            return {"error": "Aucun log trouvé."}

        total_tokens = 0
        total_cost = 0.0
        by_tier: dict[str, dict] = {}
        by_step: dict[str, int] = {}
        calls = 0

        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line.strip())
                calls += 1
                t = entry["tokens"]["total_tokens"]
                total_tokens += t
                total_cost += entry["cost_usd"]

                tier = entry.get("tier") or "classifier"
                by_tier.setdefault(tier, {"tokens": 0, "calls": 0})
                by_tier[tier]["tokens"] += t
                by_tier[tier]["calls"] += 1

                step = entry["step"]
                by_step.setdefault(step, 0)
                by_step[step] += t

        return {
            "total_calls": calls,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "tokens_by_tier": by_tier,
            "tokens_by_step": by_step,
        }
