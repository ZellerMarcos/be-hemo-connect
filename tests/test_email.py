import logging
from unittest.mock import patch

import pytest

from app.services.email import send_password_reset_email, send_two_factor_code


@pytest.fixture(autouse=True)
def resend_environment(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_secret")
    monkeypatch.setenv("MAIL_FROM", "Hemo Connect <onboarding@resend.dev>")


def test_two_factor_email_uses_resend_without_logging_code(caplog):
    with patch("app.services.email.resend.Emails.send") as send:
        with caplog.at_level(logging.INFO, logger="app.services.email"):
            send_two_factor_code("user@example.com", "123456")

    request = send.call_args.args[0]
    assert request["to"] == ["user@example.com"]
    assert request["subject"] == "Código de verificação - Hemo Connect"
    assert "123456" in request["text"]
    assert "123456" not in caplog.text
    assert "re_test_secret" not in caplog.text


def test_password_reset_email_uses_resend_without_logging_reset_url(caplog):
    reset_url = "http://localhost:5173/reset-password?token=secret-token"

    with patch("app.services.email.resend.Emails.send") as send:
        with caplog.at_level(logging.INFO, logger="app.services.email"):
            send_password_reset_email("user@example.com", reset_url)

    request = send.call_args.args[0]
    assert request["to"] == ["user@example.com"]
    assert request["subject"] == "Redefinição de senha - Hemo Connect"
    assert reset_url in request["text"]
    assert reset_url not in caplog.text
    assert "secret-token" not in caplog.text


def test_resend_failure_is_propagated_without_api_key_in_logs(caplog):
    with patch(
        "app.services.email.resend.Emails.send",
        side_effect=RuntimeError("provider failure"),
    ):
        with caplog.at_level(logging.INFO, logger="app.services.email"):
            with pytest.raises(RuntimeError, match="provider failure"):
                send_two_factor_code("user@example.com", "123456")

    assert "re_test_secret" not in caplog.text
    assert "123456" not in caplog.text
