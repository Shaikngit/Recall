from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import requests

try:
    from azure.identity import DefaultAzureCredential
except ImportError:
    DefaultAzureCredential = None


DEFAULT_GITHUB_MODELS_URL = "https://models.inference.ai.azure.com"
DEFAULT_OPENAI_URL = "https://api.openai.com/v1"
DEFAULT_AZURE_OPENAI_API_VERSION = "2024-10-21"
AZURE_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
SETTINGS_DIR = Path(__file__).resolve().parents[1] / ".mykb"
SETTINGS_PATH = SETTINGS_DIR / "model-settings.json"


@dataclass
class AISettings:
    provider: str = ""
    api_key: str = ""
    model: str = ""
    base_url: str = ""

    @property
    def is_configured(self) -> bool:
        if self.provider == "azure-openai":
            return bool(self.model and self.base_url)
        return bool(self.api_key and self.model and self.base_url)

    def to_public_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "baseUrl": self.base_url,
            "hasApiKey": bool(self.api_key),
            "configured": self.is_configured,
            "usesCliAuth": self.provider == "azure-openai" and not bool(self.api_key),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "AISettings":
        provider = str(payload.get("provider", "")).strip().lower()
        model = str(payload.get("model", "")).strip()
        base_url = str(payload.get("baseUrl", "")).strip()
        api_key = str(payload.get("apiKey", "")).strip()

        if provider == "github-models" and not base_url:
            base_url = DEFAULT_GITHUB_MODELS_URL
        if provider == "openai" and not base_url:
            base_url = DEFAULT_OPENAI_URL

        return cls(provider=provider, api_key=api_key, model=model, base_url=base_url)


class AISettingsStore:
    def __init__(self, path: Path = SETTINGS_PATH) -> None:
        self.path = path

    def load(self) -> AISettings:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            return AISettings.from_payload(data)
        return self._from_env()

    def save(self, settings: AISettings) -> AISettings:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "provider": settings.provider,
            "apiKey": settings.api_key,
            "model": settings.model,
            "baseUrl": settings.base_url,
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return settings

    def _from_env(self) -> AISettings:
        azure_model = os.getenv("AZURE_OPENAI_DEPLOYMENT", "") or os.getenv("AZURE_OPENAI_MODEL", "")
        azure_base_url = os.getenv("AZURE_OPENAI_BASE_URL", "") or os.getenv("AZURE_OPENAI_ENDPOINT", "")
        azure_api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        if azure_model and azure_base_url:
            return AISettings(
                provider="azure-openai",
                api_key=azure_api_key,
                model=azure_model,
                base_url=azure_base_url,
            )

        openai_key = os.getenv("OPENAI_API_KEY", "")
        openai_model = os.getenv("OPENAI_MODEL", "")
        openai_base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_URL)
        if openai_key and openai_model:
            return AISettings(provider="openai", api_key=openai_key, model=openai_model, base_url=openai_base_url)

        github_token = os.getenv("GITHUB_TOKEN", "")
        github_model = os.getenv("GITHUB_MODELS_MODEL", "") or os.getenv("OPENAI_MODEL", "")
        if github_token and github_model:
            return AISettings(
                provider="github-models",
                api_key=github_token,
                model=github_model,
                base_url=DEFAULT_GITHUB_MODELS_URL,
            )
        return AISettings()


@dataclass
class AIHelper:
    provider: str | None
    api_key: str | None
    model: str | None
    base_url: str | None

    @property
    def is_configured(self) -> bool:
        if self.provider == "azure-openai":
            return bool(self.model and self.base_url and (self.api_key or self._get_azure_access_token()))
        return bool(self.api_key and self.model and self.base_url)

    @classmethod
    def from_env(cls) -> "AIHelper":
        settings = AISettingsStore().load()
        return cls.from_settings(settings)

    @classmethod
    def from_settings(cls, settings: AISettings) -> "AIHelper":
        return cls(
            provider=settings.provider or None,
            api_key=settings.api_key or None,
            model=settings.model or None,
            base_url=settings.base_url or None,
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "baseUrl": self.base_url,
            "configured": self.is_configured,
        }

    def answer_question(self, query: str, context_json: str, history: list[dict[str, str]] | None = None) -> str | None:
        if not self.is_configured:
            return None
        history_text = ""
        if history:
            clipped = history[-6:]
            history_text = "\n".join(f"{item.get('role', 'user')}: {item.get('content', '')}" for item in clipped)
        prompt = (
            "You answer questions about a personal markdown knowledge base. "
            "Use only the provided note context. If the context is insufficient, say so briefly. "
            "Answer in a conversational style like a chat assistant, not like a search engine. "
            "Lead with the answer, then include only the most relevant supporting detail.\n\n"
            f"Conversation so far:\n{history_text or 'No prior conversation.'}\n\n"
            f"Question: {query}\n\n"
            f"Context:\n{context_json}"
        )
        return self._chat(prompt)

    def test_connection(self) -> tuple[bool, str]:
        if not self.is_configured:
            if self.provider == "azure-openai":
                return False, "For Azure OpenAI, provide model and base URL, plus either an API key or an active Azure CLI sign-in."
            return False, "Provider, API key, model, and base URL are required."

        prompt = "Reply with exactly: connection ok"
        response = self._chat(prompt)
        if not response:
            return False, "Connection failed. Check API key, model, and base URL."
        return True, response

    def summarize_note(self, raw_note: str) -> dict[str, str] | None:
        if not self.is_configured:
            return None
        prompt = (
            "Convert this rough incident note into compact JSON with keys title, summary, fix, learning. "
            "Use short searchable markdown-friendly phrasing. If a field is unknown, return an empty string.\n\n"
            f"Raw note:\n{raw_note}"
        )
        response = self._chat(prompt, response_format={"type": "json_object"})
        return self._parse_summary_response(response)

    def summarize_note_with_image(self, raw_note: str, image_bytes: bytes, mime_type: str) -> dict[str, str] | None:
        if not self.is_configured:
            return None

        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{encoded_image}"
        prompt = (
            "You are converting a personal knowledge-base capture into compact JSON. "
            "Read the screenshot carefully, extract the visible text, and combine it with the user's manual note. "
            "Return JSON with keys title, summary, fix, learning, extracted_text. "
            "Use short searchable markdown-friendly phrasing. If a field is unknown, return an empty string.\n\n"
            f"Manual note:\n{raw_note or '(no manual note)'}"
        )
        response = self._chat(
            [
                {
                    "role": "system",
                    "content": "You are a precise knowledge-base assistant.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=1200,
        )
        return self._parse_summary_response(response, include_extracted_text=True)

    def _parse_summary_response(self, response: str | None, include_extracted_text: bool = False) -> dict[str, str] | None:
        if not response:
            return None
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            return None
        parsed = {
            "title": str(data.get("title", "")).strip(),
            "summary": str(data.get("summary", "")).strip(),
            "fix": str(data.get("fix", "")).strip(),
            "learning": str(data.get("learning", "")).strip(),
        }
        if include_extracted_text:
            parsed["extracted_text"] = str(data.get("extracted_text", "")).strip()
        return parsed

    def transcribe_audio(self, audio_bytes: bytes) -> str | None:
        """Transcribe audio via Azure OpenAI Whisper deployment."""
        if self.provider != "azure-openai":
            return None
        headers: dict[str, str] = {}
        if self.api_key:
            headers["api-key"] = self.api_key
        else:
            token = self._get_azure_access_token()
            if not token:
                return None
            headers["Authorization"] = f"Bearer {token}"
        base_url = (self.base_url or "").rstrip("/")
        whisper_deployment = os.getenv("AZURE_OPENAI_WHISPER_DEPLOYMENT", "shaiknkb-whisper")
        url = (
            f"{base_url}/openai/deployments/{whisper_deployment}"
            f"/audio/transcriptions?api-version={DEFAULT_AZURE_OPENAI_API_VERSION}"
        )
        try:
            resp = requests.post(
                url, headers=headers,
                files={"file": ("recording.wav", audio_bytes, "audio/wav")},
                data={"response_format": "text"},
                timeout=30,
            )
            return resp.text.strip() if resp.ok else None
        except requests.RequestException:
            return None

    def _chat(
        self,
        prompt: str | list[dict[str, object]],
        response_format: dict[str, str] | None = None,
        max_tokens: int | None = None,
    ) -> str | None:
        headers = {"Content-Type": "application/json"}
        if self.provider == "azure-openai":
            if self.api_key:
                headers["api-key"] = f"{self.api_key}"
            else:
                access_token = self._get_azure_access_token()
                if not access_token:
                    return None
                headers["Authorization"] = f"Bearer {access_token}"
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": prompt
            if isinstance(prompt, list)
            else [
                {"role": "system", "content": "You are a precise knowledge-base assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        base_url = self.base_url.rstrip("/")
        if self.provider == "azure-openai":
            if base_url.endswith("/openai/v1"):
                url = f"{base_url}/chat/completions"
            else:
                payload.pop("model", None)
                url = (
                    f"{base_url}/openai/deployments/{self.model}/chat/completions"
                    f"?api-version={DEFAULT_AZURE_OPENAI_API_VERSION}"
                )
        else:
            url = f"{base_url}/chat/completions"

        response = None
        for attempt in range(3):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=30)
            except requests.RequestException:
                return None

            if response.ok:
                break

            if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                return None

            retry_after_seconds = self._retry_delay_seconds(response, attempt)
            time.sleep(retry_after_seconds)

        if response is None or not response.ok:
            return None

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = [item.get("text", "") for item in content if isinstance(item, dict)]
            joined = "\n".join(part for part in text_parts if part)
            return joined.strip() or None
        return None

    def _retry_delay_seconds(self, response: requests.Response, attempt: int) -> float:
        retry_after_ms = response.headers.get("retry-after-ms")
        if retry_after_ms:
            try:
                return max(float(retry_after_ms) / 1000.0, 1.0)
            except ValueError:
                pass

        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 1.0)
            except ValueError:
                pass

        return float(2 ** attempt)

    def _get_azure_access_token(self) -> str | None:
        cli_token = self._get_azure_cli_token()
        if cli_token:
            return cli_token

        if DefaultAzureCredential is None:
            return None

        try:
            credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
            token = credential.get_token(AZURE_COGNITIVE_SCOPE)
        except Exception:
            return None
        return token.token or None

    def _get_azure_cli_token(self) -> str | None:
        az_executable = shutil.which("az.cmd") or shutil.which("az")
        if not az_executable:
            return None
        try:
            completed = subprocess.run(
                [
                    az_executable,
                    "account",
                    "get-access-token",
                    "--resource",
                    "https://cognitiveservices.azure.com",
                    "--query",
                    "accessToken",
                    "-o",
                    "tsv",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        token = completed.stdout.strip()
        return token or None
