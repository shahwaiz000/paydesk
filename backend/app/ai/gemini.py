"""Small wrapper around Google Gemini (free tier).

Rules PayDesk follows with AI:
  * AI only EXPLAINS and SUGGESTS. It never decides a salary amount.
  * We send numbers and driver IDs only - never names, Iqama numbers, IBANs or phones.
  * If there is no key, or Gemini fails, PayDesk keeps working with its rule-based text.
"""

from __future__ import annotations

import json
import time

from ..config import BACKEND_DIR, settings

FALLBACK_MODELS = ["gemini-3.8-flash"]
RETRY_WAITS = [2, 5]             # seconds to wait when Google says "high demand" (503)
REQUEST_TIMEOUT_MS = 45_000      # one request may take at most 45 seconds
TOTAL_DEADLINE_S = 90            # all retries and model switches together: at most 90 seconds
_discovered: str | None = None   # newest working "flash" model, found automatically
_discovered_fast: str | None = None   # newest working "flash-lite" model (quick answers, e.g. driver chat)
_model_list: list[str] | None = None  # models this key can use - asked from Google once, then remembered
_client = None                        # one connection to Google, reused (faster than a new one each time)
_client_key = ""


class AIError(Exception):
    pass


def api_key() -> str:
    if settings.gemini_api_key.strip():
        return settings.gemini_api_key.strip()
    # Notepad sometimes saves .env with a hidden BOM character - read it ourselves to be safe
    env = BACKEND_DIR / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "GEMINI_API_KEY":
                return value.strip().strip('"').strip("'")
    return ""


def is_enabled() -> bool:
    return bool(api_key())


def _models(fast: bool = False) -> list[str]:
    models = [_discovered, settings.gemini_model] + FALLBACK_MODELS
    if fast:
        # quick answers: the light models first (they don't "think" first), then the normal ones
        lite = [m for m in (_model_list or []) if "lite" in m]
        models = [_discovered_fast] + lite + models
    seen: list[str] = []
    for m in models:
        if m and m not in seen:
            seen.append(m)
    return seen


def _version(name: str) -> tuple:
    nums = []
    for part in name.replace("gemini-", "").split("-")[0].split("."):
        nums.append(int(part) if part.isdigit() else 0)
    return tuple(nums)


def _discover_flash_models(client) -> list[str]:
    """Ask Google which models this key can use: newest stable 'flash' first, 'flash-lite' last.
    Google retires old model names, so this keeps PayDesk working without code changes."""
    try:
        full, lite = [], []
        for m in client.models.list():
            name = (m.name or "").removeprefix("models/")
            actions = getattr(m, "supported_actions", None) or []
            if "flash" not in name or "generateContent" not in actions:
                continue
            if any(x in name for x in ("preview", "exp", "image", "tts", "live", "audio", "latest")):
                continue
            (lite if "lite" in name else full).append(name)
        return sorted(full, key=_version, reverse=True) + sorted(lite, key=_version, reverse=True)
    except Exception:  # noqa: BLE001
        return []


def _get_client(key: str):
    global _client, _client_key
    if _client is None or _client_key != key:
        from google import genai
        from google.genai import types
        # Never wait forever: each Gemini request gives up after 45 seconds
        _client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
        _client_key = key
    return _client


def generate(prompt: str, want_json: bool = False, files: list[tuple[bytes, str]] | None = None,
             fast: bool = False) -> str:
    """files: optional [(bytes, mime_type)] - images or PDFs for Gemini to read.
    fast=True: for short answers (driver chat) - tries the quicker flash-lite models first."""
    key = api_key()
    if not key:
        raise AIError("No Gemini key. Add GEMINI_API_KEY to backend/.env and restart the backend.")
    try:
        from google import genai
    except ImportError as e:  # pragma: no cover
        raise AIError("google-genai is not installed (pip install google-genai)") from e

    from google.genai import types
    client = _get_client(key)
    global _model_list
    if fast and _model_list is None:
        _model_list = _discover_flash_models(client)   # once per backend start
    started = time.monotonic()
    deadline = started + TOTAL_DEADLINE_S
    contents: list = [prompt]
    if files:
        contents = [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in files] + [prompt]
    config = {"temperature": 0.2}
    if want_json:
        config["response_mime_type"] = "application/json"

    global _discovered, _discovered_fast
    errors: list[str] = []
    tried: set[str] = set()
    candidates = _models(fast)
    discovered_once = False
    while candidates:
        if time.monotonic() > deadline:
            errors.append("gave up after 90 seconds")
            break
        model = candidates.pop(0)
        if model in tried:
            continue
        tried.add(model)
        for attempt in range(len(RETRY_WAITS) + 1):
            try:
                response = client.models.generate_content(model=model, contents=contents, config=config)
                text = (response.text or "").strip()
                if text:
                    if fast:
                        _discovered_fast = model  # remember the one that works
                    else:
                        _discovered = model
                    print(f"[ai] {model} answered in {time.monotonic() - started:.1f} s")
                    return text
                errors.append(f"{model}: empty answer")
                break
            except Exception as e:  # noqa: BLE001 - show a friendly message, try again / next model
                msg = str(e)
                if "API key not valid" in msg or "API_KEY_INVALID" in msg:
                    raise AIError("Gemini rejected the key. Check GEMINI_API_KEY in backend/.env") from e
                busy = "503" in msg or "UNAVAILABLE" in msg or "overloaded" in msg.lower()
                if busy and attempt < len(RETRY_WAITS) and time.monotonic() < deadline:
                    time.sleep(RETRY_WAITS[attempt])   # Google is busy - wait a moment, then retry
                    continue
                if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                    errors.append(f"{model}: free limit reached")
                else:
                    errors.append(f"{model}: {'busy (high demand)' if busy else msg[:120]}")
                break
        if not candidates and not discovered_once:
            discovered_once = True
            if _model_list is None:
                _model_list = _discover_flash_models(client)
            candidates.extend(m for m in _model_list if m not in tried)
    raise AIError("Gemini couldn't answer right now - please try again in a minute. (" +
                  " | ".join(errors)[:300] + ")")


def generate_json(prompt: str, files: list[tuple[bytes, str]] | None = None):
    text = generate(prompt, want_json=True, files=files)
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise AIError("Gemini answered, but not in the expected format - try again") from e
