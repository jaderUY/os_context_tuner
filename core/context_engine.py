from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml


class ContextEngine:
    """Evalúa el contexto actual y selecciona la receta YAML aplicable."""

    def __init__(self, recipes_dir: Path):
        self.recipes_dir = Path(recipes_dir)

    def load_recipes(self) -> List[Dict[str, Any]]:
        """Carga todas las recetas válidas (.yaml / .yml) desde el directorio."""
        if not self.recipes_dir.exists():
            return []

        recipes: List[Dict[str, Any]] = []
        for file_path in sorted(self.recipes_dir.glob("*.y*ml")):
            try:
                with file_path.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if isinstance(data, dict) and data.get("enabled", True):
                    data.setdefault("name", file_path.stem)
                    recipes.append(data)
            except Exception as exc:
                print(f"[ContextEngine] Error leyendo '{file_path.name}': {exc}")

        # Mayor prioridad primero (por defecto 0)
        recipes.sort(key=lambda r: r.get("priority", 0), reverse=True)
        return recipes

    def evaluate(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Devuelve la receta de mayor prioridad cuyas condiciones coincidan con el contexto."""
        for recipe in self.load_recipes():
            conditions = recipe.get("conditions", {})
            if self._matches(conditions, context):
                return recipe
        return None

    @staticmethod
    def _matches(conditions: Dict[str, Any], context: Dict[str, Any]) -> bool:
        if not conditions:
            return True

        if "ac_online" in conditions and context.get("ac_online") != conditions["ac_online"]:
            return False

        if "max_battery_percent" in conditions:
            battery = context.get("battery_percent")
            if battery is None or battery > conditions["max_battery_percent"]:
                return False

        if "min_battery_percent" in conditions:
            battery = context.get("battery_percent")
            if battery is None or battery < conditions["min_battery_percent"]:
                return False

        return True

