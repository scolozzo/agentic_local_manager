from app_core import provider_validation


class _FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_gitlab_validation_falls_back_to_bearer(monkeypatch):
    responses = [
        _FakeResponse(401, text="unauthorized"),
        _FakeResponse(200, payload={"username": "tester"}),
    ]

    def fake_get(url, headers, timeout):
        assert url.endswith("/api/v4/user")
        return responses.pop(0)

    monkeypatch.setattr(provider_validation.requests, "get", fake_get)

    result = provider_validation.validate_git_credentials("gitlab", "token", "https://gitlab.com/api/v4")

    assert result["ok"] is True
    assert result["username"] == "tester"
