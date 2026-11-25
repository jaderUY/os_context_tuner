import json
import time
from typing import Any, Dict

import pywintypes
import win32con
import win32file
import win32pipe
import winerror

PIPE_NAME = r"\\.\pipe\OSContextTunerPipe"
BUFFER_SIZE = 65536


class NamedPipeIPCClient:
    """Cliente IPC ligero que envía comandos JSON al servicio elevado via Named Pipe."""

    def __init__(self, pipe_name: str = PIPE_NAME, timeout_ms: int = 3000):
        self.pipe_name = pipe_name
        self.timeout_ms = timeout_ms

    def send_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            deadline = time.monotonic() + self.timeout_ms / 1000
            while True:
                remaining = deadline - time.monotonic()
                try:
                    win32pipe.WaitNamedPipe(
                        self.pipe_name, max(1, int(remaining * 1000))
                    )
                    break
                except pywintypes.error as exc:
                    retry_in = deadline - time.monotonic()
                    if exc.winerror != winerror.ERROR_FILE_NOT_FOUND or retry_in <= 0:
                        raise
                    time.sleep(min(0.05, retry_in))

            handle = win32file.CreateFile(
                self.pipe_name,
                win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )
            try:
                win32pipe.SetNamedPipeHandleState(
                    handle, win32pipe.PIPE_READMODE_MESSAGE, None, None
                )
                encoded = json.dumps(payload).encode("utf-8")
                win32file.WriteFile(handle, encoded)
                _, raw_resp = win32file.ReadFile(handle, BUFFER_SIZE)
                return json.loads(raw_resp.decode("utf-8"))
            finally:
                win32file.CloseHandle(handle)

        except pywintypes.error as exc:
            return {
                "status": "error",
                "message": f"No se pudo comunicar con el servicio IPC (WinError {exc.winerror})",
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

