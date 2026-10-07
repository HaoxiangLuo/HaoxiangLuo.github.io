#!/usr/bin/env python3
"""One small OpenAI-compatible chat client shared by the site's generators.

Why this exists: every script here used to call GitHub Models directly
(`models.github.ai/inference/chat/completions` with the workflow's
`GITHUB_TOKEN`). GitHub Models was retired on 2026-07-30 — the playground,
the model catalog, the inference API and BYOK are all gone, and the host now
answers every request with a plain "OK" — so the endpoint, the key and the
model are configuration instead of constants.

Configuration (all read from the environment, never committed):

    TRANSLATE_BASE_URL   base URL of an OpenAI-compatible service, e.g.
                         https://api.groq.com/openai/v1
                         `/chat/completions` is appended when missing.
    TRANSLATE_API_KEY    its API key. Falls back to GITHUB_MODELS_TOKEN and
                         then GITHUB_TOKEN when those are all that is set.
    TRANSLATE_MODEL      the model id, default "gpt-4o-mini".

Nothing is sent unless a provider is configured: `TRANSLATE_BASE_URL` or
`TRANSLATE_API_KEY` must be present, otherwise `configured()` is False and the
callers leave their fields pending. That keeps the old GITHUB_TOKEN-only
workflows from spending a request per field on an endpoint that no longer
serves inference.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_ENDPOINT = "https://models.github.ai/inference/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
TIMEOUT = 20
USER_AGENT = "HaoxiangLuo.github.io model client/1.0"


class ModelUnavailable(RuntimeError):
    """The endpoint refused the request or replied with something unusable."""


def endpoint() -> str:
    base = (os.environ.get("TRANSLATE_BASE_URL") or DEFAULT_ENDPOINT).strip().rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


def api_key() -> str:
    return (
        os.environ.get("TRANSLATE_API_KEY")
        or os.environ.get("GITHUB_MODELS_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    ).strip()


def model() -> str:
    return (os.environ.get("TRANSLATE_MODEL") or DEFAULT_MODEL).strip()


def configured() -> bool:
    """True when a provider has been pointed at explicitly.

    The default endpoint is the retired GitHub one, so a bare GITHUB_TOKEN is
    not treated as a working provider.
    """
    return bool(os.environ.get("TRANSLATE_BASE_URL") or os.environ.get("TRANSLATE_API_KEY"))


def snippet(raw: bytes | str, limit: int = 200) -> str:
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    return repr(text.replace("\n", " ").replace("\r", " ").strip()[:limit])


def chat(messages: list[dict], timeout: int = TIMEOUT, response_format: dict | None = None) -> str:
    """Return the assistant reply, or raise ModelUnavailable with the reason."""
    request_body = {"model": model(), "messages": messages, "temperature": 0.2}
    if response_format:
        request_body["response_format"] = response_format
    payload = json.dumps(request_body).encode("utf-8")
    request = urllib.request.Request(
        endpoint(),
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise ModelUnavailable(
            f"{endpoint()} returned HTTP {exc.code} ({exc.reason}): {snippet(exc.read())}"
        ) from exc
    except Exception as exc:  # noqa: BLE001 - network failures of any kind
        raise ModelUnavailable(f"{endpoint()} could not be reached: {exc}") from exc
    try:
        body = json.loads(raw.decode("utf-8", "replace"))
    except ValueError as exc:
        raise ModelUnavailable(
            f"{endpoint()} replied HTTP {status} with a non-JSON body: {snippet(raw)}"
        ) from exc
    try:
        return body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelUnavailable(
            f"{endpoint()} replied without a choice: {snippet(raw)}"
        ) from exc


GTX_ENDPOINT = "https://translate.googleapis.com/translate_a/single"


def public_translate(text: str, target: str = "zh") -> str:
    """Translate through Google's unauthenticated web endpoint.

    This is the endpoint the daily-news collector has always fallen back on:
    it needs no key and no configuration, so the site keeps producing Chinese
    even when no provider is configured. The trade-off is that it is an
    unofficial endpoint — Google may rate-limit or close it without notice —
    and its wording is blunter than a model's. It is therefore only ever
    reached when no provider is configured or the provider refused.
    """
    source, destination = ("en", "zh-CN") if target == "zh" else ("zh-CN", "en")
    query = urllib.parse.urlencode(
        {"client": "gtx", "sl": source, "tl": destination, "dt": "t", "q": text}
    )
    request = urllib.request.Request(
        f"{GTX_ENDPOINT}?{query}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        body = json.loads(response.read().decode("utf-8"))
    segments = body[0] if body else []
    return "".join(segment[0] for segment in segments if segment and segment[0])
