import urllib.request
import urllib.error
import json
import uuid
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("GoveeStreamController.API")

class GoveeAPIClient:
    BASE_URL = "https://openapi.api.govee.com"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _send_request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.error("Govee API Key is not configured.")
            return None

        url = f"{self.BASE_URL}{path}"
        headers = {
            "Govee-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = response.read().decode("utf-8")
                if res_data:
                    return json.loads(res_data)
                return {}
        except urllib.error.HTTPError as e:
            try:
                err_content = e.read().decode("utf-8")
            except Exception:
                err_content = ""
            logger.error(f"HTTP Error {e.code}: {err_content or e.reason}")
            return None
        except Exception as e:
            logger.error(f"Error sending request to Govee API: {e}")
            return None

    def get_devices(self) -> List[Dict[str, Any]]:
        """
        Retrieves all devices associated with the account.
        Endpoint: GET /router/api/v1/user/devices
        """
        response = self._send_request("GET", "/router/api/v1/user/devices")
        if response and response.get("code") == 200:
            return response.get("data", {}).get("devices", [])
        return []

    def get_device_state(self, device: str, sku: str) -> Optional[Dict[str, Any]]:
        """
        Queries the current state of a device.
        Endpoint: POST /router/api/v1/device/state
        """
        request_id = str(uuid.uuid4())
        body = {
            "requestId": request_id,
            "payload": {
                "sku": sku,
                "device": device
            }
        }
        response = self._send_request("POST", "/router/api/v1/device/state", body)
        if response and response.get("code") == 200:
            return response.get("data", {})
        return None

    def control_device(self, device: str, sku: str, capability_type: str, instance: str, value: Any) -> bool:
        """
        Controls a device capability (e.g. power, brightness, color).
        Endpoint: POST /router/api/v1/device/control
        """
        request_id = str(uuid.uuid4())
        body = {
            "requestId": request_id,
            "payload": {
                "sku": sku,
                "device": device,
                "capability": {
                    "type": capability_type,
                    "instance": instance,
                    "value": value
                }
            }
        }
        response = self._send_request("POST", "/router/api/v1/device/control", body)
        if response and response.get("code") == 200:
            return True
        return False

    def get_scenes(self, device: str, sku: str) -> List[Dict[str, Any]]:
        """
        Retrieves available scenes for a specific device.
        Endpoint: POST /router/api/v1/device/scenes
        """
        request_id = str(uuid.uuid4())
        body = {
            "requestId": request_id,
            "payload": {
                "sku": sku,
                "device": device
            }
        }
        response = self._send_request("POST", "/router/api/v1/device/scenes", body)
        if response and response.get("code") == 200:
            capabilities = response.get("payload", {}).get("capabilities", [])
            for cap in capabilities:
                if (cap.get("type") == "devices.capabilities.dynamic_scene" and 
                    cap.get("instance") == "lightScene"):
                    return cap.get("parameters", {}).get("options", [])
        return []
