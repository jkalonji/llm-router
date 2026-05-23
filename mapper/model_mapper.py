"""
mapper/model_mapper.py
Charge la matrice YAML et résout catégorie → tier → modèle.
"""

import yaml
from pathlib import Path
from dataclasses import dataclass


MATRIX_PATH = Path(__file__).parent / "models.yaml"


@dataclass
class ModelSpec:
    tier: str
    model: str
    description: str
    cost_per_million_input_tokens: float
    cost_per_million_output_tokens: float


@dataclass
class ClassifierConfig:
    model: str
    fallback_model: str | None
    max_tokens: int
    temperature: float


class ModelMapper:
    def __init__(self, matrix_path: Path = MATRIX_PATH):
        with open(matrix_path, "r", encoding="utf-8") as f:
            self._matrix = yaml.safe_load(f)

    def get_model_for_category(self, category: str) -> ModelSpec:
        """Retourne le ModelSpec pour une catégorie donnée."""
        categories = self._matrix["categories"]
        if category not in categories:
            raise ValueError(
                f"Catégorie inconnue : '{category}'. "
                f"Catégories valides : {list(categories.keys())}"
            )
        tier_name = categories[category]["tier"]
        return self._get_model_for_tier(tier_name)

    def _get_model_for_tier(self, tier: str) -> ModelSpec:
        tiers = self._matrix["tiers"]
        if tier not in tiers:
            raise ValueError(f"Tier inconnu : '{tier}'. Tiers valides : {list(tiers.keys())}")
        t = tiers[tier]
        return ModelSpec(
            tier=tier,
            model=t["model"],
            description=t["description"],
            cost_per_million_input_tokens=t["cost_per_million_input_tokens"],
            cost_per_million_output_tokens=t["cost_per_million_output_tokens"],
        )

    def get_classifier_config(self) -> ClassifierConfig:
        c = self._matrix["classifier"]
        return ClassifierConfig(
            model=c["model"],
            fallback_model=c.get("fallback_model"),
            max_tokens=c["max_tokens"],
            temperature=c["temperature"],
        )

    def all_categories(self) -> list[str]:
        return list(self._matrix["categories"].keys())
