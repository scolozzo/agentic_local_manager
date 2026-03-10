from __future__ import annotations

from datetime import datetime

import requests


def validate_git_credentials(provider: str, token: str, host: str = "") -> dict:
    resolved_provider = (provider or "").strip().lower()
    token = (token or "").strip()
    if not token:
        return {"ok": False, "error": "Token vacio"}
    if resolved_provider == "github":
        return _validate_github_token(token, host)
    if resolved_provider == "gitlab":
        return _validate_gitlab_token(token, host)
    return {"ok": False, "error": f"Proveedor git no soportado: {provider}"}


def validate_llm_service(service_id: str, service: dict, api_key: str = "") -> dict:
    mode = service.get("mode", "api")
    if mode == "manual_login":
        return {
            "ok": False,
            "manual_only": True,
            "available": False,
            "validated": False,
            "message": "Este servicio requiere login manual y no puede verificarse por API desde el instalador.",
        }
    token = (api_key or "").strip()
    if not token:
        return {"ok": False, "error": "API key vacia", "available": False, "validated": False}

    base_url = (service.get("base_url") or "").rstrip("/")
    if not base_url:
        return {"ok": False, "error": "Base URL no configurada", "available": False, "validated": False}

    test_model = service.get("models", [""])[0]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    extra_headers = service.get("headers", {})
    headers.update(extra_headers)

    validation_mode = service.get("validation_mode") or ("chat" if service_id == "minimax_api" else "models")
    try:
        if validation_mode == "models":
            response = requests.get(f"{base_url}/models", headers=headers, timeout=12)
        else:
            payload = {
                "model": test_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            }
            response = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=20)
        if 200 <= response.status_code < 300:
            return {
                "ok": True,
                "available": True,
                "validated": True,
                "validated_at": datetime.utcnow().isoformat(),
                "message": "Servicio validado correctamente.",
            }
        return {
            "ok": False,
            "available": False,
            "validated": False,
            "error": f"HTTP {response.status_code}: {response.text[:240]}",
        }
    except Exception as exc:
        return {"ok": False, "available": False, "validated": False, "error": str(exc)}


def _validate_github_token(token: str, host: str = "") -> dict:
    api_root = (host or "https://api.github.com").rstrip("/")
    response = requests.get(
        f"{api_root}/user",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=12,
    )
    if 200 <= response.status_code < 300:
        payload = response.json()
        return {
            "ok": True,
            "validated": True,
            "provider": "github",
            "host": api_root,
            "username": payload.get("login", ""),
            "validated_at": datetime.utcnow().isoformat(),
        }
    return {"ok": False, "error": f"GitHub HTTP {response.status_code}: {response.text[:240]}"}


def _validate_gitlab_token(token: str, host: str = "") -> dict:
    api_root = (host or "https://gitlab.com/api/v4").rstrip("/")
    if not api_root.endswith("/api/v4"):
        api_root = api_root + "/api/v4"
    attempts = (
        {"PRIVATE-TOKEN": token},
        {"Authorization": f"Bearer {token}"},
    )
    last_response = None
    for headers in attempts:
        response = requests.get(
            f"{api_root}/user",
            headers=headers,
            timeout=12,
        )
        last_response = response
        if 200 <= response.status_code < 300:
            payload = response.json()
            return {
                "ok": True,
                "validated": True,
                "provider": "gitlab",
                "host": api_root,
                "username": payload.get("username", ""),
                "validated_at": datetime.utcnow().isoformat(),
            }
    return {"ok": False, "error": f"GitLab HTTP {last_response.status_code}: {last_response.text[:240]}"}
