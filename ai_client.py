#!/usr/bin/env python3
"""
Universal AI Provider Client for LinkedIn Content Studio.

Supports offline Local Templates plus Google Gemini, OpenAI, Anthropic Claude,
OpenRouter, Ollama (local), and any OpenAI-compatible custom endpoint using
zero third-party dependencies (Python standard library only).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
SECRETS_PATH = BASE_DIR / ".ai_secrets.json"

_RAW_PRESETS: dict[str, dict[str, Any]] = {
    "local_templates": {
        "label": "Local Templates",
        "protocol": "none",
        "requires_key": False,
        "description": "Offline structured templates (no AI API needed)",
    },
    "gemini": {
        "label": "Google Gemini",
        "protocol": "gemini",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-2.5-flash",
        "suggested_models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
        "env_var": "GEMINI_API_KEY",
        "description": "Google AI Studio Gemini models",
    },
    "openai": {
        "label": "OpenAI",
        "protocol": "openai_compat",
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "suggested_models": ["gpt-4o-mini", "gpt-4o", "o3-mini"],
        "env_var": "OPENAI_API_KEY",
        "description": "OpenAI GPT & reasoning models",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "protocol": "anthropic",
        "default_base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-sonnet-4-20250514",
        "suggested_models": ["claude-sonnet-4-20250514", "claude-3-5-haiku-latest"],
        "env_var": "ANTHROPIC_API_KEY",
        "description": "Claude Messages API",
    },
    "openrouter": {
        "label": "OpenRouter",
        "protocol": "openai_compat",
        "default_base_url": "https://openrouter.ai/api/v1",
        "default_model": "google/gemini-2.5-flash",
        "suggested_models": [
            "google/gemini-2.5-flash",
            "anthropic/claude-sonnet-4",
            "openai/gpt-4o-mini",
            "meta-llama/llama-3.3-70b-instruct",
        ],
        "env_var": "OPENROUTER_API_KEY",
        "description": "One key for 200+ models",
    },
    "ollama": {
        "label": "Ollama (Local)",
        "protocol": "openai_compat",
        "default_base_url": "http://127.0.0.1:11434/v1",
        "default_model": "llama3.2",
        "suggested_models": ["llama3.2", "qwen2.5", "mistral", "gemma3"],
        "requires_key": False,
        "description": "Run open models locally with zero API key",
    },
    "custom": {
        "label": "Custom Endpoint",
        "protocol": "openai_compat",
        "default_base_url": "http://127.0.0.1:1234/v1",
        "default_model": "local-model",
        "env_var": "AI_API_KEY",
        "requires_key": False,
        "description": "Any OpenAI-compatible API (LM Studio, Groq, DeepSeek, vLLM, etc.)",
    },
}

PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    pid: {
        "id": pid,
        "default_base_url": "",
        "default_model": "",
        "suggested_models": [],
        "env_var": "",
        "requires_key": True,
        **spec,
    }
    for pid, spec in _RAW_PRESETS.items()
}


def _clamp_temp(value: Any, default: float = 0.7, strict: bool = False) -> float:
    try:
        temp = float(default if value is None else value)
    except (TypeError, ValueError) as exc:
        if strict:
            raise ValueError("temperature must be a number.") from exc
        return default
    if strict and not 0.0 <= temp <= 2.0:
        raise ValueError("temperature must be between 0.0 and 2.0.")
    return max(0.0, min(2.0, temp))


def load_secrets() -> dict[str, str]:
    """Load saved provider API keys from .ai_secrets.json."""
    if not SECRETS_PATH.is_file():
        return {}
    try:
        data = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if v}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_secrets(secrets: dict[str, str]) -> None:
    """Persist provider API keys with owner-only permissions (0600)."""
    cleaned = {str(k): str(v).strip() for k, v in secrets.items() if str(v).strip()}
    SECRETS_PATH.write_text(json.dumps(cleaned, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(SECRETS_PATH, 0o600)
    except OSError:
        pass


def resolve_api_key(provider: str, explicit_key: str | None = None) -> str:
    """Resolve API key from explicit override, saved secrets file, or env var."""
    if explicit_key and str(explicit_key).strip():
        return str(explicit_key).strip()
    if saved := load_secrets().get(provider, "").strip():
        return saved
    env_var = PROVIDER_PRESETS.get(provider, {}).get("env_var", "")
    return os.environ.get(env_var, "").strip() if env_var else ""


def mask_key(key: str) -> str:
    """Mask an API key for safe display in the UI."""
    val = (key or "").strip()
    if not val:
        return ""
    return "••••" if len(val) < 10 else f"{val[:4]}...{val[-4:]}"


def get_ai_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Read and normalize active AI configuration from config.json."""
    raw_ai = config.get("ai")
    if isinstance(raw_ai, dict) and raw_ai.get("provider") in PROVIDER_PRESETS:
        provider = raw_ai["provider"]
        preset = PROVIDER_PRESETS[provider]
        return {
            "provider": provider,
            "model": str(raw_ai.get("model") or preset["default_model"]).strip(),
            "base_url": str(raw_ai.get("base_url") or preset["default_base_url"]).strip(),
            "temperature": _clamp_temp(raw_ai.get("temperature", 0.7)),
        }

    if os.environ.get("GEMINI_API_KEY", "").strip():
        preset = PROVIDER_PRESETS["gemini"]
        return {
            "provider": "gemini",
            "model": str(config.get("gemini_model") or preset["default_model"]).strip(),
            "base_url": preset["default_base_url"],
            "temperature": 0.7,
        }

    return {"provider": "local_templates", "model": "", "base_url": "", "temperature": 0.7}


def get_public_ai_state(config: dict[str, Any]) -> dict[str, Any]:
    """Return UI-safe AI configuration state without ever exposing raw API keys."""
    ai = get_ai_settings(config)
    provider = ai["provider"]
    preset = PROVIDER_PRESETS[provider]
    saved_keys = {pid: mask_key(resolve_api_key(pid)) for pid in PROVIDER_PRESETS}

    if provider == "local_templates":
        active_ready = False
        active_label = "Local Templates"
    else:
        has_key = bool(resolve_api_key(provider))
        active_ready = bool(ai["model"] and (has_key if preset["requires_key"] else ai["base_url"]))
        short = preset["label"].replace("Google ", "").replace("Anthropic ", "").replace(" (Local)", "")
        active_label = f"{short} · {ai['model']}" if ai["model"] else short

    return {
        "ai": ai,
        "presets": PROVIDER_PRESETS,
        "saved_keys": saved_keys,
        "active_ready": active_ready,
        "active_label": active_label,
    }


def save_ai_settings(config_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and save AI provider configuration + optional API key."""
    provider = str(payload.get("provider") or "local_templates").strip()
    if provider not in PROVIDER_PRESETS:
        raise ValueError(f"Unsupported provider '{provider}'.")
    preset = PROVIDER_PRESETS[provider]

    model = str(payload.get("model") if "model" in payload else preset["default_model"]).strip()
    base_url = str(payload.get("base_url") if "base_url" in payload else preset["default_base_url"]).strip()
    temperature = _clamp_temp(payload.get("temperature", 0.7), strict=True)

    if provider == "local_templates":
        model, base_url = "", ""
    elif not model or not base_url:
        raise ValueError("Please specify both a model name and an API base URL.")

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    cfg["ai"] = {
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "temperature": round(temperature, 2),
    }
    config_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    secrets = load_secrets()
    if payload.get("clear_api_key"):
        secrets.pop(provider, None)
        save_secrets(secrets)
    elif api_key := str(payload.get("api_key") or "").strip():
        secrets[provider] = api_key
        save_secrets(secrets)

    return cfg


def _http_json(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Send an HTTP JSON request using urllib and raise readable RuntimeErrors."""
    req_headers = {"User-Agent": "LinkedInContentStudio/1.0", **(headers or {})}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        msg = body[:300]
        try:
            err_json = json.loads(body)
            if isinstance(err_json, dict):
                err_obj = err_json.get("error")
                if isinstance(err_obj, dict) and err_obj.get("message"):
                    msg = str(err_obj["message"])
                elif isinstance(err_obj, str):
                    msg = err_obj
                elif err_json.get("message"):
                    msg = str(err_json["message"])
        except Exception:
            pass
        raise RuntimeError(f"HTTP {exc.code}: {msg or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Connection failed: {exc}") from exc


def _resolve_effective(
    config: dict[str, Any], override: dict[str, Any] | None
) -> tuple[str, dict[str, Any], str, str, float, str]:
    saved = get_ai_settings(config)
    ov = override or {}
    provider = str(ov.get("provider") or saved["provider"]).strip()
    if provider not in PROVIDER_PRESETS:
        raise ValueError(f"Unsupported provider '{provider}'.")
    preset = PROVIDER_PRESETS[provider]
    same = provider == saved["provider"]
    model = str(ov["model"] if ov.get("model") is not None else (saved["model"] if same else preset["default_model"])).strip()
    base_url = str(ov["base_url"] if ov.get("base_url") is not None else (saved["base_url"] if same else preset["default_base_url"])).strip()
    temperature = _clamp_temp(ov.get("temperature", saved.get("temperature", 0.7)))
    return provider, preset, model, base_url, temperature, resolve_api_key(provider, ov.get("api_key"))


def generate_text(
    prompt: str,
    config: dict[str, Any],
    system_prompt: str = "",
    timeout: int = 35,
    override: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Generate text from the configured AI provider/model."""
    provider, preset, model, base_url, temperature, api_key = _resolve_effective(config, override)
    protocol = preset["protocol"]
    if protocol == "none":
        raise RuntimeError("Local Templates mode is active; select an AI provider first.")
    if not model or not base_url:
        raise RuntimeError(f"Missing model or base URL for {preset['label']}.")
    if preset["requires_key"] and not api_key:
        raise RuntimeError(f"Missing API key for {preset['label']}.")

    base = base_url.rstrip("/")
    sys_text = system_prompt.strip()

    if protocol == "gemini":
        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        if sys_text:
            body["systemInstruction"] = {"parts": [{"text": sys_text}]}
        data = _http_json(
            f"{base}/models/{model}:generateContent",
            method="POST",
            headers={"x-goog-api-key": api_key},
            payload=body,
            timeout=timeout,
        )
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Unexpected Gemini API response format.") from exc
        return str(text).strip(), f"{provider}:{model}"

    if protocol == "anthropic":
        body = {
            "model": model,
            "max_tokens": 1200,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if sys_text:
            body["system"] = sys_text
        data = _http_json(
            f"{base}/messages",
            method="POST",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            payload=body,
            timeout=timeout,
        )
        blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text").strip()
        if not text:
            raise RuntimeError("Empty response from Anthropic API.")
        return text, f"{provider}:{model}"

    messages = ([{"role": "system", "content": sys_text}] if sys_text else []) + [{"role": "user", "content": prompt}]
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    if provider == "openrouter":
        headers.update({"HTTP-Referer": "http://127.0.0.1:8765", "X-Title": "LinkedIn Content Studio"})

    data = _http_json(
        f"{base}/chat/completions",
        method="POST",
        headers=headers,
        payload={"model": model, "temperature": temperature, "messages": messages},
        timeout=timeout,
    )
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected OpenAI-compatible API response format.") from exc
    return str(content).strip(), f"{provider}:{model}"


def test_connection(config: dict[str, Any], override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run a quick test prompt against the selected provider."""
    provider, preset, model, _, _, _ = _resolve_effective(config, override)
    if provider == "local_templates":
        return {"ok": True, "message": "Local Templates mode active (offline, no API needed)."}
    started = time.monotonic()
    try:
        reply, _ = generate_text("Reply with exactly: OK", config, timeout=15, override=override)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": True,
            "message": f"Connected to {preset['label']} ({model}) in {elapsed_ms}ms — reply: {reply[:40]}",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def fetch_available_models(
    config: dict[str, Any], override: dict[str, Any] | None = None
) -> list[str]:
    """Fetch available model IDs from the selected provider endpoint."""
    _, preset, _, base_url, _, api_key = _resolve_effective(config, override)
    protocol = preset["protocol"]
    if protocol in {"none", "anthropic"}:
        return list(preset["suggested_models"])
    if not base_url:
        raise RuntimeError("Please provide an API base URL first.")
    if preset["requires_key"] and not api_key:
        raise RuntimeError(f"Enter an API key for {preset['label']} to fetch models.")

    base = base_url.rstrip("/")
    if protocol == "gemini":
        data = _http_json(f"{base}/models", headers={"x-goog-api-key": api_key}, timeout=15)
        models = [
            str(m.get("name", "")).removeprefix("models/")
            for m in data.get("models", [])
            if not (m.get("supportedGenerationMethods") and "generateContent" not in m["supportedGenerationMethods"])
            and m.get("name")
        ]
        return models[:40] or list(preset["suggested_models"])

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    data = _http_json(f"{base}/models", headers=headers, timeout=15)
    models = sorted({str(m["id"]) for m in data.get("data", []) if isinstance(m, dict) and m.get("id")})
    return models[:50] or list(preset["suggested_models"])
