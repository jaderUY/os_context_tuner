from abc import ABC, abstractmethod
import ctypes
import subprocess
from typing import Dict, Any


class BaseOSDriver(ABC):
    """Interfaz abstracta para aislar la lógica específica de cada sistema operativo."""

    @abstractmethod
    def get_system_context(self) -> Dict[str, Any]:
        """Obtiene métricas/estado actual del sistema relevante para el contexto."""

    @abstractmethod
    def set_power_plan(self, plan_guid: str) -> bool:
        """Activa un plan de energía específico en el sistema."""

    @abstractmethod
    def apply_recipe(self, recipe: Dict[str, Any]) -> Dict[str, Any]:
        """Aplica un diccionario de configuración proveniente de una receta YAML."""


class Windows11Driver(BaseOSDriver):
    """Implementación concreta del driver para Windows 11."""

    # GUIDs estándar de planes de energía en Windows
    POWER_PLANS = {
        "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
        "high_performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
        "power_saver": "a1841308-3541-4fab-bc81-f71556f20b4a",
    }

    def get_system_context(self) -> Dict[str, Any]:
        """Consulta estado básico de energía (AC/batería y porcentaje) vía Win32 API."""
        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", ctypes.c_byte),
                ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte),
                ("SystemStatusFlag", ctypes.c_byte),
                ("BatteryLifeTime", ctypes.c_ulong),
                ("BatteryFullLifeTime", ctypes.c_ulong),
            ]

        status = SYSTEM_POWER_STATUS()
        ac_online = None
        battery_pct = None

        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            ac_online = status.ACLineStatus == 1
            if status.BatteryLifePercent != 255:
                battery_pct = int(status.BatteryLifePercent)

        return {
            "os": "windows_11",
            "ac_online": ac_online,
            "battery_percent": battery_pct,
        }

    def set_power_plan(self, plan_guid_or_alias: str) -> bool:
        """Cambia el plan de energía activo usando powercfg."""
        guid = self.POWER_PLANS.get(plan_guid_or_alias.lower(), plan_guid_or_alias)
        try:
            result = subprocess.run(
                ["powercfg", "/setactive", guid],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def apply_recipe(self, recipe: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta los ajustes definidos dentro de una receta."""
        results: Dict[str, Any] = {}
        settings = recipe.get("settings", {})

        if "power_plan" in settings:
            plan = settings["power_plan"]
            results["power_plan"] = {
                "target": plan,
                "applied": self.set_power_plan(plan),
            }

        return results

