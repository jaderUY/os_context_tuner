import sys
from pathlib import Path
import win32event
import win32service
import win32serviceutil
import servicemanager

# Garantiza que la raíz del proyecto (os_context_tuner) esté en sys.path bajo SYSTEM / pythonservice.exe
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from service.ipc_server import NamedPipeIPCServer

class OSContextTunerService(win32serviceutil.ServiceFramework):
    _svc_name_ = "OSContextTunerService"
    _svc_display_name_ = "OS Context Tuner Background Service"
    _svc_description_ = (
        "Servicio en segundo plano con privilegios elevados para aplicar perfiles "
        "y ajustes del sistema operativo mediante IPC seguro."
    )

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, True, False, None)
        self.ipc_server = NamedPipeIPCServer(handler=self.procesar_comando_ipc)

    def procesar_comando_ipc(self, payload: dict) -> dict:
        """
        Punto central donde el servicio recibe órdenes desde la UI o el motor de contexto.
        Más adelante aquí conectaremos con core.os_driver.
        """
        action = payload.get("action")
        if action == "ping":
            return {"status": "ok", "service": self._svc_name_, "message": "Servicio operativo"}
        if action == "apply_profile":
            profile_name = payload.get("profile", "default")
            # TODO: delegar a OSDriver cuando esté implementado
            return {"status": "ok", "message": f"Perfil '{profile_name}' recibido por el servicio"}
        return {"status": "error", "message": f"Acción no soportada: {action}"}

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        servicemanager.LogInfoMsg(f"{self._svc_name_}: Deteniendo servicio...")
        self.ipc_server.stop()
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self.ipc_server.start()

        # Espera hasta que se invoque SvcStop
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)

        servicemanager.LogInfoMsg(f"{self._svc_name_}: Servicio detenido limpiamente.")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(OSContextTunerService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(OSContextTunerService)

