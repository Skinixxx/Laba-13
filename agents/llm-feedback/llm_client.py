import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger("llm_client")


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "tinyllama"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def _request(self, method: str, path: str, data: dict | None = None) -> dict | None:
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            logger.error(f"Ollama HTTP {e.code}: {e.read().decode()}")
            return None
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            return None

    def is_available(self) -> bool:
        result = self._request("GET", "/api/tags")
        return result is not None

    def generate(self, prompt: str, system: str = "") -> str | None:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 512},
        }
        if system:
            payload["system"] = system
        result = self._request("POST", "/api/generate", payload)
        if result and "response" in result:
            return result["response"].strip()
        return None

    def list_models(self) -> list[str]:
        result = self._request("GET", "/api/tags")
        if result and "models" in result:
            return [m["name"] for m in result["models"]]
        return []
