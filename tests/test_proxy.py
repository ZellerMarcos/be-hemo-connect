import pytest
from unittest.mock import patch
from datetime import timedelta
from fastapi import Request
from fastapi.testclient import TestClient

from app.main import app
from app.security.rate_limit import (
    _scope_key,
    enforce_public_endpoint_limits,
    request_origin,
)
from scripts.serve import DeploymentProxyHeaders, TRUSTED_PROXY_PEERS


@pytest.mark.parametrize("peer,expected_client,expected_scheme", [
    ("198.51.100.10", "198.51.100.10", "http"),
    ("127.0.0.1", "203.0.113.20", "https"),
])
@pytest.mark.anyio
async def test_server_only_normalizes_explicit_loopback_proxy(
    peer, expected_client, expected_scheme,
):
    captured = {}

    async def downstream(scope, receive, send):
        captured.update(scope)

    middleware = DeploymentProxyHeaders(downstream, trusted_hosts=("127.0.0.1", "::1"))
    scope = {
        "type": "http", "scheme": "http", "client": (peer, 1000),
        "headers": [
            (b"x-forwarded-for", b"192.0.2.99,203.0.113.20"),
            (b"x-forwarded-proto", b"https"),
        ],
    }
    await middleware(scope, None, None)
    assert captured["client"][0] == expected_client
    assert captured["scheme"] == expected_scheme
    assert captured["state"]["verified_proxy_peer"] == (
        peer if peer == "127.0.0.1" else None
    )


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_application_ignores_forged_protocol_header(monkeypatch):
    monkeypatch.setattr("app.main.is_production", True)
    client = TestClient(app, base_url="http://testserver")
    response = client.get(
        "/health", headers={"X-Forwarded-Proto": "https"}, follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == "https://testserver/health"


def test_normalized_https_does_not_redirect_back_to_itself(monkeypatch):
    monkeypatch.setattr("app.main.is_production", True)
    client = TestClient(app, base_url="https://testserver")
    response = client.get(
        "/health", headers={"X-Forwarded-Proto": "http"}, follow_redirects=False,
    )
    assert response.status_code == 200


@pytest.mark.parametrize("host", ["localhost.attacker.invalid", "127.0.0.1.attacker.invalid"])
def test_host_prefix_cannot_bypass_https(monkeypatch, host):
    monkeypatch.setattr("app.main.is_production", True)
    client = TestClient(app, base_url=f"http://{host}")
    assert client.get("/health", follow_redirects=False).status_code == 307


def test_deployment_does_not_presume_proxy_trust():
    assert TRUSTED_PROXY_PEERS == ()
    with pytest.raises(ValueError):
        DeploymentProxyHeaders(app, trusted_hosts=("*",))
    with pytest.raises(ValueError):
        DeploymentProxyHeaders(app, trusted_hosts=("10.0.0.0/8",))


@pytest.mark.parametrize("peer,client,expected", [
    (None, "198.51.100.10", None),
    ("192.0.2.10", "192.0.2.10", None),
    ("192.0.2.10", "203.0.113.20", "203.0.113.20"),
    ("192.0.2.10", "invalid", None),
])
def test_origin_in_production_requires_verified_normalization(
    monkeypatch, peer, client, expected,
):
    monkeypatch.setenv("APP_ENV", "production")
    request = Request({
        "type": "http", "client": (client, 1234),
        "state": {"verified_proxy_peer": peer},
        "headers": [(b"x-forwarded-for", b"203.0.113.99")],
    })
    assert request_origin(request) == expected


def test_unverified_origin_keeps_global_and_account_protection(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    request = Request({
        "type": "http", "client": ("192.0.2.10", 1234), "headers": [],
    })
    with patch("app.security.rate_limit.enforce_rate_limit") as enforce:
        enforce_public_endpoint_limits(
            None, request, action="login", account_identifier="user@example.com",
            account_limit=3, origin_limit=10, global_limit=100,
            window=timedelta(minutes=15),
        )
    assert [call.kwargs["scope"] for call in enforce.call_args_list] == [
        "global", "account",
    ]


def test_digest_is_normalized_and_separates_operations_and_scopes():
    first = _scope_key("login", "account", " User@Example.COM ")
    assert first == _scope_key("login", "account", "user@example.com")
    assert len(first) == 64
    assert first != _scope_key("reset", "account", "user@example.com")
    assert first != _scope_key("login", "origin", "user@example.com")
