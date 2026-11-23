import json
import threading

from pathlib import Path
from typing import Any, Dict
from communication.api_client import BackendAPIClient
from communication.ws_client import AgentWebSocketClient
from core.context_engine import ContextEngine
from core.os_driver import Windows11Driver
from ui.ipc_client import NamedPipeIPCClient
from ui.tray_app import OSContextTunerTray

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"


def load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    if not path.exists():
        return {
            "api_base_url": "https://oct-backend-api.onrender.com",
            "ws_url": "wss://oct-backend-api.onrender.com/ws/agent",
            "device_id": "win11-local-dev",
            "access_token": None,
            "recipes_dir": "config/recipes",
            "context_poll_interval_sec": 15,
        }
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: Dict[str, Any], path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def main() -> None:
    cfg = load_config()
    recipes_dir = BASE_DIR / cfg.get("recipes_dir", "config/recipes")
    recipes_dir.mkdir(parents=True, exist_ok=True)

    driver = Windows11Driver()
    engine = ContextEngine(recipes_dir=recipes_dir)
    ipc_client = NamedPipeIPCClient()

    api_client = BackendAPIClient(
        base_url=cfg.get("api_base_url", "https://oct-backend-api.onrender.com"),
        access_token=cfg.get("access_token"),
    )

    stop_watcher = threading.Event()
    tray_ref: Dict[str, OSContextTunerTray] = {}

    def apply_profile_via_service(profile_name: str) -> None:
        resp = ipc_client.send_command({"action": "apply_profile", "profile": profile_name})
        print(f"[Main] Respuesta IPC para perfil '{profile_name}': {resp}")
        tray = tray_ref.get("instance")
        if tray and resp.get("status") == "ok":
            tray.active_profile = profile_name
            tray.service_status = "Conectado"
            tray._update_visual_state(connected=True)

    def handle_ws_message(message: Dict[str, Any]) -> None:
        print(f"[Main] Mensaje recibido por WebSocket: {message}")
        if message.get("event") == "apply_profile" and message.get("profile"):
            apply_profile_via_service(message["profile"])

    def handle_sync_requested() -> None:
        print("[Main] Sincronización con backend solicitada...")
        try:
            health = api_client.health_check()
            print(f"[Main] Backend disponible: {health}")
        except Exception as exc:
            print(f"[Main] No se pudo sincronizar con el backend: {exc}")

    def context_watcher_loop() -> None:
        last_applied_recipe = None
        interval = max(3, int(cfg.get("context_poll_interval_sec", 15)))

        while not stop_watcher.is_set():
            try:
                ctx = driver.get_system_context()
                matched_recipe = engine.evaluate(ctx)
                if matched_recipe:
                    recipe_name = matched_recipe.get("name")
                    target_plan = matched_recipe.get("settings", {}).get("power_plan")
                    if target_plan and recipe_name != last_applied_recipe:
                        print(f"[ContextWatcher] Contexto coincide con receta '{recipe_name}' -> '{target_plan}'")
                        apply_profile_via_service(target_plan)
                        last_applied_recipe = recipe_name
            except Exception as exc:
                print(f"[ContextWatcher] Error evaluando contexto: {exc}")

            stop_watcher.wait(interval)

    ws_client = AgentWebSocketClient(
        ws_url=cfg.get("ws_url", "wss://oct-backend-api.onrender.com/ws/agent"),
        on_message_callback=handle_ws_message,
    )
    ws_client.start()

    watcher_thread = threading.Thread(target=context_watcher_loop, name="ContextWatcher", daemon=True)
    watcher_thread.start()

    tray = OSContextTunerTray(
        ipc_client=ipc_client,
        on_sync_requested=handle_sync_requested,
    )
    tray_ref["instance"] = tray

    try:
        tray.run()
    finally:
        stop_watcher.set()
        ws_client.stop()
        print("[Main] Agente detenido limpiamente.")


if __name__ == "__main__":
    main()
    