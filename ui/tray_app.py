import threading
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw

from ui.ipc_client import NamedPipeIPCClient


class OSContextTunerTray:
    """Interfaz minimalista en la bandeja del sistema (System Tray) para Windows 11."""

    def __init__(
        self,
        ipc_client: Optional[NamedPipeIPCClient] = None,
        on_sync_requested: Optional[Callable[[], None]] = None,
    ):
        self.ipc = ipc_client or NamedPipeIPCClient()
        self.on_sync_requested = on_sync_requested
        self.active_profile = "balanced"
        self.service_status = "Desconocido"
        self._icon: Optional[pystray.Icon] = None

    @staticmethod
    def _create_icon_image(connected: bool = True) -> Image.Image:
        """Genera un ícono vectorial liviano en memoria sin depender de archivos externos."""
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Fondo circular oscuro y anillo de estado (azul activo / gris desconectado)
        ring_color = (0, 120, 215, 255) if connected else (130, 130, 130, 255)
        draw.ellipse((4, 4, 60, 60), fill=(24, 24, 28, 255), outline=ring_color, width=5)
        draw.ellipse((22, 22, 42, 42), fill=ring_color)
        return img

    def _run_async(self, target: Callable[[], None]):
        threading.Thread(target=target, daemon=True).start()

    def _update_visual_state(self, connected: bool):
        if self._icon:
            self._icon.icon = self._create_icon_image(connected=connected)
            self._icon.title = f"OS Context Tuner | Perfil: {self.active_profile} ({self.service_status})"
            self._icon.update_menu()

    def check_service_health(self):
        def _task():
            resp = self.ipc.send_command({"action": "ping"})
            ok = resp.get("status") == "ok"
            self.service_status = "Conectado" if ok else "Sin conexión"
            print(f"[UI] Estado del servicio: {resp}")
            self._update_visual_state(connected=ok)

        self._run_async(_task)

    def select_profile(self, profile_name: str):
        def _handler(icon, item):
            def _task():
                resp = self.ipc.send_command(
                    {"action": "apply_profile", "profile": profile_name}
                )
                if resp.get("status") == "ok":
                    self.active_profile = profile_name
                    self.service_status = "Conectado"
                    self._update_visual_state(connected=True)
                else:
                    self.service_status = "Error IPC"
                    self._update_visual_state(connected=False)
                print(f"[UI] Cambio de perfil '{profile_name}': {resp}")

            self._run_async(_task)

        return _handler

    def _trigger_sync(self, icon, item):
        if self.on_sync_requested:
            self._run_async(self.on_sync_requested)

    def _exit_app(self, icon, item):
        icon.stop()

    def _build_menu(self) -> pystray.Menu:
        profiles_submenu = pystray.Menu(
            pystray.MenuItem(
                "Equilibrado (Balanced)",
                self.select_profile("balanced"),
                checked=lambda item: self.active_profile == "balanced",
                radio=True,
            ),
            pystray.MenuItem(
                "Alto Rendimiento (High Performance)",
                self.select_profile("high_performance"),
                checked=lambda item: self.active_profile == "high_performance",
                radio=True,
            ),
            pystray.MenuItem(
                "Ahorro de Energía (Power Saver)",
                self.select_profile("power_saver"),
                checked=lambda item: self.active_profile == "power_saver",
                radio=True,
            ),
        )

        return pystray.Menu(
            pystray.MenuItem(
                lambda text: f"Servicio: {self.service_status}",
                lambda icon, item: self.check_service_health(),
            ),
            pystray.MenuItem(
                lambda text: f"Perfil activo: {self.active_profile}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Cambiar perfil manualmente", profiles_submenu),
            pystray.MenuItem("Sincronizar con la nube", self._trigger_sync),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Verificar conexión IPC", lambda icon, item: self.check_service_health()),
            pystray.MenuItem("Salir", self._exit_app),
        )

    def run(self):
        self._icon = pystray.Icon(
            name="OSContextTuner",
            icon=self._create_icon_image(connected=False),
            title="OS Context Tuner (Iniciando...)",
            menu=self._build_menu(),
        )
        # Verificar el estado del servicio apenas arranque el ícono
        self.check_service_health()
        self._icon.run()