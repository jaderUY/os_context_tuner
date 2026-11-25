import json
import threading
from typing import Callable, Dict, Any, Optional

import pywintypes
import winerror
import win32event
import win32con
import win32file
import win32pipe
import win32process
import win32security

PIPE_NAME = r"\\.\pipe\OSContextTunerPipe"
BUFFER_SIZE = 65536


def construir_security_attributes_estricto() -> win32security.SECURITY_ATTRIBUTES:
    """
    Crea una SECURITY_ATTRIBUTES con DACL estricta:
    - SYSTEM (SY): Acceso total
    - Built-in Administrators (BA): Acceso total
    - Usuario interactivo actual (si aplica en pruebas locales): Lectura/Escritura
    """
    sd = win32security.SECURITY_DESCRIPTOR()
    dacl = win32security.ACL()

    sid_system = win32security.ConvertStringSidToSid("S-1-5-18")          # Local System
    sid_admins = win32security.ConvertStringSidToSid("S-1-5-32-544")      # Administrators

    # Permisos genéricos de lectura y escritura en pipe
    pipe_rw_access = win32con.GENERIC_READ | win32con.GENERIC_WRITE

    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.GENERIC_ALL, sid_system)
    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.GENERIC_ALL, sid_admins)

    # Opcional: permitir al usuario que lanza el proceso de prueba si no es SYSTEM/Admin
    try:
        token = win32security.OpenProcessToken(
            win32process.GetCurrentProcess(), win32security.TOKEN_QUERY
        )
        user_sid, _ = win32security.GetTokenInformation(token, win32security.TokenUser)
        dacl.AddAccessAllowedAce(win32security.ACL_REVISION, pipe_rw_access, user_sid)
    except pywintypes.error:
        pass

    sd.SetSecurityDescriptorDacl(True, dacl, False)

    sa = win32security.SECURITY_ATTRIBUTES()
    sa.SECURITY_DESCRIPTOR = sd
    sa.bInheritHandle = False
    return sa


class NamedPipeIPCServer:
    def __init__(
        self,
        pipe_name: str = PIPE_NAME,
        handler: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ):
        self.pipe_name = pipe_name
        self.handler = handler or self._default_handler
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def _default_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        action = payload.get("action")
        if action == "ping":
            return {"status": "ok", "message": "Servicio OS Context Tuner activo"}
        return {"status": "ignored", "message": f"Acción no reconocida: {action}"}

    def _crear_pipe_instancia(self, sa: win32security.SECURITY_ATTRIBUTES):
        return win32pipe.CreateNamedPipe(
            self.pipe_name,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
            win32pipe.PIPE_UNLIMITED_INSTANCES,
            BUFFER_SIZE,
            BUFFER_SIZE,
            0,
            sa,
        )

    def _serve_loop(self):
        sa = construir_security_attributes_estricto()

        while not self._stop_event.is_set():
            pipe_handle = None
            try:
                pipe_handle = self._crear_pipe_instancia(sa)

                # Evento overlappeado para poder cancelar ConnectNamedPipe al detener el servicio
                connect_event = win32event.CreateEvent(None, True, False, None)
                overlapped = pywintypes.OVERLAPPED()
                overlapped.hEvent = connect_event

                try:
                    win32pipe.ConnectNamedPipe(pipe_handle, overlapped)
                except pywintypes.error as e:
                    if e.winerror == winerror.ERROR_PIPE_CONNECTED:
                        pass
                    elif e.winerror == winerror.ERROR_IO_PENDING:
                        while not self._stop_event.is_set():
                            rc = win32event.WaitForSingleObject(connect_event, 250)
                            if rc == win32event.WAIT_OBJECT_0:
                                break
                        if self._stop_event.is_set():
                            win32file.CancelIo(pipe_handle)
                            break
                    else:
                        raise
                finally:
                    win32file.CloseHandle(connect_event)

                if self._stop_event.is_set():
                    break

                # Leer petición del cliente
                _, raw_data = win32file.ReadFile(pipe_handle, BUFFER_SIZE)
                if raw_data:
                    try:
                        request_data = json.loads(raw_data.decode("utf-8"))
                        response_data = self.handler(request_data)
                    except json.JSONDecodeError:
                        response_data = {"status": "error", "message": "JSON inválido"}
                    except Exception as exc:
                        response_data = {"status": "error", "message": str(exc)}

                    encoded_resp = json.dumps(response_data).encode("utf-8")
                    win32file.WriteFile(pipe_handle, encoded_resp)

                win32file.FlushFileBuffers(pipe_handle)

            except pywintypes.error as e:
                if not self._stop_event.is_set():
                    print(f"[IPC] Error de Win32 en Named Pipe: {e}")
            finally:
                if pipe_handle:
                    try:
                        win32pipe.DisconnectNamedPipe(pipe_handle)
                    except pywintypes.error:
                        pass
                    win32file.CloseHandle(pipe_handle)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._serve_loop, name="NamedPipeIPCServer", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)