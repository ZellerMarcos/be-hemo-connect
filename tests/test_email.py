import logging
from unittest.mock import patch

import httpx
import pytest

from app.services.email import send_password_reset_email, send_two_factor_code


@pytest.fixture(autouse=True)
def brevo_environment(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib_test_secret")
    monkeypatch.setenv("MAIL_FROM", "hemoconnect.projeto@gmail.com")
    monkeypatch.setenv("MAIL_FROM_NAME", "Hemo Connect")


def test_two_factor_email_uses_brevo_without_logging_code(caplog):
    with patch("app.services.email.httpx.post") as send:
        with caplog.at_level(logging.INFO, logger="app.services.email"):
            send_two_factor_code("user@example.com", "123456")

    url = send.call_args.args[0]
    request = send.call_args.kwargs
    assert url == "https://api.brevo.com/v3/smtp/email"
    assert request["headers"]["api-key"] == "xkeysib_test_secret"
    assert request["json"]["to"] == [{"email": "user@example.com"}]
    assert request["json"]["subject"] == "Código de verificação - Hemo Connect"
    assert "123456" in request["json"]["textContent"]
    assert "123456" not in caplog.text
    assert "xkeysib_test_secret" not in caplog.text


def test_password_reset_email_uses_brevo_without_logging_reset_url(caplog):
    reset_url = "http://localhost:5173/reset-password?token=secret-token"

    with patch("app.services.email.httpx.post") as send:
        with caplog.at_level(logging.INFO, logger="app.services.email"):
            send_password_reset_email("user@example.com", reset_url)

    request = send.call_args.kwargs
    assert request["json"]["to"] == [{"email": "user@example.com"}]
    assert request["json"]["subject"] == "Redefinição de senha - Hemo Connect"
    assert reset_url in request["json"]["textContent"]
    assert reset_url not in caplog.text
    assert "secret-token" not in caplog.text


def test_brevo_failure_is_propagated_without_api_key_in_logs(caplog):
    with patch(
        "app.services.email.httpx.post",
        side_effect=httpx.RequestError("provider failure"),
    ):
        with caplog.at_level(logging.INFO, logger="app.services.email"):
            with pytest.raises(httpx.RequestError, match="provider failure"):
                send_two_factor_code("user@example.com", "123456")

    assert "xkeysib_test_secret" not in caplog.text
    assert "123456" not in caplog.text


def test_brevo_timeout_is_propagated_without_sensitive_logging(caplog):
    with patch(
        "app.services.email.httpx.post",
        side_effect=httpx.TimeoutException("provider timeout"),
    ):
        with caplog.at_level(logging.INFO, logger="app.services.email"):
            with pytest.raises(httpx.TimeoutException, match="provider timeout"):
                send_password_reset_email(
                    "user@example.com",
                    "http://localhost:5173/reset-password?token=secret-token",
                )

    assert "xkeysib_test_secret" not in caplog.text
    assert "secret-token" not in caplog.text


def test_brevo_http_failure_is_propagated_without_response_logging(caplog):
    response = httpx.Response(401, request=httpx.Request("POST", "https://api.brevo.com/v3/smtp/email"))
    with patch("app.services.email.httpx.post", return_value=response):
        with caplog.at_level(logging.INFO, logger="app.services.email"):
            with pytest.raises(httpx.HTTPStatusError):
                send_two_factor_code("user@example.com", "123456")

    assert "401" not in caplog.text
    assert "xkeysib_test_secret" not in caplog.text
    assert "123456" not in caplog.text
