import json
import threading
import time
from typing import Any, Callable, Dict, Optional

import websocket


class AgentWebSocketClient:
    """Cliente WebSocket resiliente con reconexión automática para eventos en tiempo real."""

    def __init__(
        self,
        ws_url: str = "ws://127.0.0.1:8000/ws/agent",
        on_message_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        reconnect_delay: float = 5.0,
    ):
        self.ws_url = ws_url
        self.on_message_callback = on_message_callback
        self.reconnect_delay = reconnect_delay

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ws_app: Optional[websocket.WebSocketApp] = None

    def _handle_message(self, _ws, message: str):
        if not self.on_message_callback:
            return
        try:
            parsed = json.loads(message)
        except json.JSONDecodeError:
            parsed = {"raw": message}
        self.on_message_callback(parsed)

    def _handle_error(self, _ws, error):
        if not self._stop_event.is_set():
            print(f"[WS] Error de conexión: {error}")

    def _handle_close(self, _ws, close_status_code, close_msg):
        if not self._stop_event.is_set():
            print(f"[WS] Conexión cerrada ({close_status_code}): {close_msg}")

    def _run_loop(self):
        while not self._stop_event.is_set():
            self._ws_app = websocket.WebSocketApp(
                self.ws_url,
                on_message=self._handle_message,
                on_error=self._handle_error,
                on_close=self._handle_close,
            )
            self._ws_app.run_forever(ping_interval=25, ping_timeout=10)

            if not self._stop_event.is_set():
                time.sleep(self.reconnect_delay)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="AgentWebSocketClient", daemon=True)
        self._thread.start()

    def send_json(self, data: Dict[str, Any]) -> bool:
        if self._ws_app and self._ws_app.sock and self._ws_app.sock.connected:
            self._ws_app.send(json.dumps(data))
            return True
        return False

    def stop(self):
        self._stop_event.set()
        if self._ws_app:
            try:
                self._ws_app.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

