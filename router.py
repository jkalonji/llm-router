"""
router.py
Orchestrateur principal du LLM Router.

Deux modes :
- "recommendation" : classifie et retourne le plan JSON (appelé par un chatbot/LLM)
- "execution"      : classifie, exécute chaque sous-tâche sur le bon modèle Groq,
                     retourne les réponses (appelé par un agent IA)
"""

import os
import time
from dataclasses import dataclass, asdict
from typing import Optional

from groq import Groq, APIError, APIStatusError

from classifier.classifier import Classifier, SubTask, ClassifierError
from mapper.model_mapper import ModelMapper
from logger import RouterLogger


@dataclass
class SubTaskResult:
    subtask_index: int
    tache: str
    categorie: str
    tier: str
    model: str
    response: Optional[str]          # None en mode recommendation
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    latency_ms: Optional[int]


@dataclass
class RouterResult:
    mode: str
    original_prompt: str
    subtasks: list[SubTaskResult]

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "original_prompt": self.original_prompt,
            "subtasks": [asdict(s) for s in self.subtasks],
        }


class Router:
    def __init__(self):
        self.mapper = ModelMapper()
        self.logger = RouterLogger()
        self.classifier = Classifier(mapper=self.mapper, logger=self.logger)

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ClassifierError("GROQ_API_KEY manquante.")
        self.groq_client = Groq(api_key=api_key)

    def route(self, prompt: str, mode: str = "recommendation") -> RouterResult:
        """
        Point d'entrée principal.
        mode = "recommendation" | "execution"
        """
        if mode not in ("recommendation", "execution"):
            raise ValueError(f"Mode invalide : '{mode}'. Valeurs acceptées : recommendation, execution")

        subtasks: list[SubTask] = self.classifier.classify(prompt, mode=mode)

        results: list[SubTaskResult] = []

        for subtask in subtasks:
            if mode == "recommendation":
                results.append(SubTaskResult(
                    subtask_index=subtask.subtask_index,
                    tache=subtask.tache,
                    categorie=subtask.categorie,
                    tier=subtask.tier,
                    model=subtask.model,
                    response=None,
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    latency_ms=None,
                ))
            else:
                result = self._execute_subtask(prompt, subtask, mode)
                results.append(result)

        return RouterResult(
            mode=mode,
            original_prompt=prompt,
            subtasks=results,
        )

    def _execute_subtask(self, original_prompt: str, subtask: SubTask, mode: str) -> SubTaskResult:
        """
        Exécute une sous-tâche sur le modèle Groq approprié.
        Pour les requêtes mixtes, on passe le prompt original + contexte de la sous-tâche.
        """
        # Construire le prompt d'exécution pour cette sous-tâche
        if subtask.subtask_index == 0:
            execution_prompt = original_prompt
        else:
            execution_prompt = (
                f"Dans le cadre de la tâche suivante : '{subtask.tache}'\n\n"
                f"Prompt original : {original_prompt}"
            )

        model_spec = self.mapper.get_model_for_category(subtask.categorie)
        start = time.monotonic()

        try:
            response = self.groq_client.chat.completions.create(
                model=subtask.model,
                messages=[{"role": "user", "content": execution_prompt}],
                max_tokens=2048,
                temperature=0.7,
            )
        except APIStatusError as e:
            raise ClassifierError(
                f"Modèle '{subtask.model}' indisponible sur Groq (HTTP {e.status_code}) "
                f"pour la sous-tâche '{subtask.tache}'."
            ) from e
        except APIError as e:
            raise ClassifierError(
                f"Erreur API Groq lors de l'exécution de '{subtask.tache}' : {e}"
            ) from e

        latency_ms = int((time.monotonic() - start) * 1000)

        # Logger cet appel d'inférence
        log_entry = self.logger.build_entry(
            mode=mode,
            step="inference",
            model=subtask.model,
            prompt=execution_prompt,
            usage=response.usage,
            latency_ms=latency_ms,
            cost_per_million_input=model_spec.cost_per_million_input_tokens,
            cost_per_million_output=model_spec.cost_per_million_output_tokens,
            category=subtask.categorie,
            tier=subtask.tier,
            subtask_index=subtask.subtask_index,
            subtask_label=subtask.tache,
        )
        self.logger.log(log_entry)

        return SubTaskResult(
            subtask_index=subtask.subtask_index,
            tache=subtask.tache,
            categorie=subtask.categorie,
            tier=subtask.tier,
            model=subtask.model,
            response=response.choices[0].message.content,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            latency_ms=latency_ms,
        )
