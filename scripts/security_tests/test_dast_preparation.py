import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app_factory = load_module("dast_app")
preparation = load_module("prepare_dast")


class DastPreparationTests(unittest.TestCase):
    def test_synthetic_accounts_pass_real_login_email_validation(self):
        from app.schemas.auth import LoginRequest

        for address in app_factory.SYNTHETIC_RECIPIENTS:
            request = LoginRequest(email=address, senha="synthetic-password")
            self.assertEqual(str(request.email), address)

    def test_prepare_requires_real_second_factor_and_keeps_tokens_private(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "private"
            output = Path(directory) / "output"
            private.mkdir()
            account = {"role": "doador", "email": "doador@example.com", "password": "synthetic-password"}
            (private / "credentials.json").write_text(json.dumps([account]))
            (private / "outbox.json").write_text(json.dumps([
                {"recipient": account["email"], "body": "Code: 123456"},
            ]))
            verified = []

            def handler(request):
                if request.url.path == "/openapi.json":
                    return httpx.Response(200, json={
                        "openapi": "3.1.0", "paths": {"/auth/me": {"get": {"responses": {}}}},
                    })
                if request.url.path == "/auth/login":
                    return httpx.Response(200, json={
                        "requires_2fa": True, "challenge_id": "synthetic-id",
                        "challenge_secret": "synthetic-secret",
                    })
                if request.url.path == "/auth/2fa/verify":
                    verified.append(json.loads(request.content))
                    return httpx.Response(200, json={"access_token": "synthetic-session"})
                self.assertEqual(request.headers["authorization"], "Bearer synthetic-session")
                return httpx.Response(200, json=[])

            client = httpx.Client(base_url=preparation.TARGET, transport=httpx.MockTransport(handler))
            with patch.object(preparation.httpx, "Client", return_value=client):
                preparation.prepare(private, output)
            self.assertEqual(verified[0]["code"], "123456")
            plan = yaml.safe_load((private / "doador-plan.yaml").read_text())
            self.assertEqual(plan["jobs"][-1]["parameters"]["errorExitValue"], 1)
            self.assertEqual(plan["jobs"][-1]["parameters"]["errorLevel"], "High")
            self.assertNotIn("synthetic-session", (output / "coverage.json").read_text())

    def test_refuses_non_ci_and_non_loopback_databases(self):
        for values in ({}, {"HEMO_DAST_ISOLATED": "1", "APP_ENV": "production"}, {
            "HEMO_DAST_ISOLATED": "1", "APP_ENV": "ci",
            "DATABASE_URL": "postgresql+psycopg://hemo_dast:synthetic@remote.invalid/hemo_dast",
        }, {
            "HEMO_DAST_ISOLATED": "1", "APP_ENV": "ci",
            "DATABASE_URL": "postgresql+psycopg://hemo_dast:synthetic@127.0.0.1/production",
        }):
            with patch.dict(os.environ, values, clear=True), self.assertRaises(RuntimeError):
                app_factory.validate_environment()

    def test_accepts_only_explicit_disposable_database(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {
                "HEMO_DAST_ISOLATED": "1", "APP_ENV": "ci",
                "DATABASE_URL": "postgresql+psycopg://hemo_dast:synthetic@127.0.0.1/hemo_dast",
                "DAST_PRIVATE_DIR": directory,
            }, clear=True):
                self.assertEqual(app_factory.validate_environment(), Path(directory).resolve())

    def test_sanitize_does_not_publish_session_token(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "private"
            output = Path(directory) / "output"
            private.mkdir()
            output.mkdir()
            (private / "redactions.json").write_text(json.dumps(["synthetic-session"]))
            report = output / "zap-doador.json"
            report.write_text('{"evidence":"Bearer synthetic-session"}')
            preparation.sanitize(private, output)
            self.assertNotIn("synthetic-session", report.read_text())
            self.assertIn("[REDACTED]", report.read_text())


if __name__ == "__main__":
    unittest.main()
