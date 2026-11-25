from typing import Any, Dict, Optional
import requests


class BackendAPIClient:
    """Cliente HTTP para comunicarse con la API FastAPI del OS Context Tuner."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        access_token: Optional[str] = None,
        timeout: int = 10,
    ):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def health_check(self) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/", headers=self._headers(), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def login(self, email: str, password: str) -> Dict[str, Any]:
        payload = {"email": email, "contraseña": password}
        resp = requests.post(
            f"{self.base_url}/api/auth/login",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if token:
            self.access_token = token
        return data

    def get_user(self, id_usuario: str) -> Dict[str, Any]:
        resp = requests.get(
            f"{self.base_url}/api/users/{id_usuario}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def register_device(self, device_payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = requests.post(
            f"{self.base_url}/api/devices",
            json=device_payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def get_profile(self, id_controlador: str) -> Dict[str, Any]:
        resp = requests.get(
            f"{self.base_url}/api/profiles/{id_controlador}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def update_profile(self, profile_payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = requests.post(
            f"{self.base_url}/api/profiles/update",
            json=profile_payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

