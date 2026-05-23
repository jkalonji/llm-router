"""
classifier/classifier.py
Appelle GPT-OSS 120B via Groq pour classifier un prompt en sous-tâches atomiques.
Utilise du chain-of-thought structuré. Retourne une liste de SubTask.
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

from groq import Groq, APIError, APIStatusError

from mapper.model_mapper import ModelMapper, ModelSpec
from logger import RouterLogger


SYSTEM_PROMPT = """You are a task routing classifier for an LLM router system.

Your job: analyze the user's prompt and decompose it into atomic subtasks.
For each subtask, assign exactly one category from this list:
- reflexion   → complex reasoning, strategy, multi-step analysis, dissertation
- code        → code generation, debugging, algorithms, math calculations
- resume      → summarization, key point extraction, condensing documents
- traduction  → translation between languages, reformulation in another language
- execution   → reformatting, simple extraction, template filling, parsing, listing

Rules:
1. If the prompt is a single task, return a list with one item.
2. If the prompt mixes multiple tasks, decompose into sequential atomic subtasks.
3. Use the language of the user's prompt in the "tache" field.
4. Think step by step before outputting (chain-of-thought inside <thinking> tags).
5. Output ONLY valid JSON after </thinking> — no markdown, no explanation.

Output format (JSON array):
[
  {"tache": "<short description of subtask>", "categorie": "<category>", "tier": "<petit|moyen|gros>"}
]

Tier mapping (fixed):
- reflexion → gros
- code → moyen
- resume → moyen
- traduction → petit
- execution → petit
"""


@dataclass
class SubTask:
    tache: str
    categorie: str
    tier: str
    model: str
    subtask_index: int


class ClassifierError(Exception):
    """Erreur explicite du classifieur — pas de fallback silencieux."""
    pass


class Classifier:
    def __init__(self, mapper: ModelMapper, logger: RouterLogger):
        self.mapper = mapper
        self.logger = logger
        self.config = mapper.get_classifier_config()

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ClassifierError(
                "GROQ_API_KEY manquante. "
                "Créez un fichier .env avec GROQ_API_KEY=votre_clé ou exportez la variable."
            )
        self.client = Groq(api_key=api_key)

    def classify(self, prompt: str, mode: str = "recommendation") -> list[SubTask]:
        """
        Classifie un prompt en sous-tâches atomiques.
        mode : "recommendation" | "execution"
        Lève ClassifierError si le modèle est indisponible ou si la réponse est invalide.
        """
        start = time.monotonic()

        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
        except APIStatusError as e:
            if e.status_code in (404, 503):
                model_name = self.config.model
                raise ClassifierError(
                    f"Modèle classifieur indisponible sur Groq : '{model_name}' "
                    f"(HTTP {e.status_code}). "
                    f"Vérifiez la disponibilité du modèle sur https://console.groq.com/docs/models. "
                    f"Aucun fallback configuré — erreur explicite selon la spec POC."
                ) from e
            raise ClassifierError(f"Erreur API Groq : {e}") from e
        except APIError as e:
            raise ClassifierError(f"Erreur API Groq : {e}") from e

        latency_ms = int((time.monotonic() - start) * 1000)
        usage = response.choices[0].message  # on extrait usage depuis response
        raw_content = response.choices[0].message.content

        # Log de l'appel classifieur
        log_entry = self.logger.build_entry(
            mode=mode,
            step="classifier",
            model=self.config.model,
            prompt=prompt,
            usage=response.usage,
            latency_ms=latency_ms,
        )
        self.logger.log(log_entry)

        # Extraire le JSON (après le bloc <thinking> éventuel)
        subtasks_raw = self._parse_json_from_response(raw_content)

        # Résoudre le modèle pour chaque sous-tâche
        subtasks = []
        for i, item in enumerate(subtasks_raw):
            self._validate_subtask_dict(item, index=i)
            model_spec: ModelSpec = self.mapper.get_model_for_category(item["categorie"])
            subtasks.append(
                SubTask(
                    tache=item["tache"],
                    categorie=item["categorie"],
                    tier=item["tier"],
                    model=model_spec.model,
                    subtask_index=i,
                )
            )

        return subtasks

    def _parse_json_from_response(self, content: str) -> list[dict]:
        """Extrait le JSON de la réponse, en ignorant le bloc <thinking>."""
        # Supprimer le bloc chain-of-thought si présent
        if "</thinking>" in content:
            content = content.split("</thinking>", 1)[1].strip()

        # Nettoyer les éventuels blocs markdown
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise ClassifierError(
                f"Le classifieur n'a pas retourné du JSON valide.\n"
                f"Contenu reçu :\n{content}\n"
                f"Erreur JSON : {e}"
            ) from e

        if not isinstance(parsed, list):
            raise ClassifierError(
                f"Le classifieur doit retourner une liste JSON. Reçu : {type(parsed).__name__}"
            )

        return parsed

    def _validate_subtask_dict(self, item: dict, index: int) -> None:
        required_keys = {"tache", "categorie", "tier"}
        missing = required_keys - set(item.keys())
        if missing:
            raise ClassifierError(
                f"Sous-tâche #{index} incomplète. Clés manquantes : {missing}. Reçu : {item}"
            )
        valid_categories = self.mapper.all_categories()
        if item["categorie"] not in valid_categories:
            raise ClassifierError(
                f"Catégorie invalide '{item['categorie']}' dans la sous-tâche #{index}. "
                f"Catégories valides : {valid_categories}"
            )
        valid_tiers = {"petit", "moyen", "gros"}
        if item["tier"] not in valid_tiers:
            raise ClassifierError(
                f"Tier invalide '{item['tier']}' dans la sous-tâche #{index}. "
                f"Tiers valides : {valid_tiers}"
            )
