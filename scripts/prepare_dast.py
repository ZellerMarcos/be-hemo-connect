import argparse
import json
import re
from pathlib import Path

import httpx
import yaml


TARGET = "http://127.0.0.1:8000"


def prepare(private: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    coverage = []
    with httpx.Client(base_url=TARGET, timeout=15, follow_redirects=False) as client:
        schema_response = client.get("/openapi.json")
        schema_response.raise_for_status()
        schema = schema_response.json()
        tokens = []
        for account in json.loads((private / "credentials.json").read_text(encoding="utf-8")):
            login = client.post("/auth/login", json={
                "email": account["email"], "senha": account["password"],
            })
            login.raise_for_status()
            challenge = login.json()
            if "access_token" in challenge or not challenge.get("requires_2fa"):
                raise RuntimeError("Primary authentication must not emit a session.")
            messages = json.loads((private / "outbox.json").read_text(encoding="utf-8"))
            message = next(item for item in reversed(messages) if item["recipient"] == account["email"])
            code = re.search(r"\b\d{6}\b", message["body"])
            if code is None:
                raise RuntimeError("Local adapter did not capture the 2FA code.")
            response = client.post("/auth/2fa/verify", json={
                "challenge_id": challenge["challenge_id"],
                "challenge_secret": challenge["challenge_secret"], "code": code.group(),
            })
            response.raise_for_status()
            token = response.json()["access_token"]
            tokens.append(token)
            paths = ["/auth/me", "/usuarios", "/hemocentros", "/hemocentros/1"]
            if account["role"] == "doador":
                paths.extend(["/agendamentos/me", "/historico/me"])
            for path in paths:
                result = client.get(path, headers={"Authorization": f"Bearer {token}"})
                result.raise_for_status()
                coverage.append({"role": account["role"], "path": path, "status": result.status_code})
            definition = {
                **schema,
                "servers": [{"url": TARGET}],
                "paths": {
                    path: {"get": schema["paths"][path]["get"]}
                    for path in paths if path in schema["paths"]
                },
            }
            role = account["role"]
            definition_file = private / f"{role}-openapi.json"
            definition_file.write_text(json.dumps(definition), encoding="utf-8")
            plan = {
                "env": {
                    "contexts": [{"name": role, "urls": [TARGET],
                                  "includePaths": [r"http://127\.0\.0\.1:8000/.*"]}],
                    "parameters": {"failOnError": True, "failOnWarning": True, "progressToStdout": False},
                },
                "jobs": [
                    {"type": "replacer", "rules": [{
                        "description": "Isolated synthetic session",
                        "url": r"http://127\.0\.0\.1:8000/.*",
                        "matchType": "req_header", "matchString": "Authorization",
                        "matchRegex": False, "replacementString": f"Bearer {token}",
                    }]},
                    {"type": "openapi", "parameters": {
                        "apiFile": f"/zap/private/{role}-openapi.json", "targetUrl": TARGET, "context": role,
                    }},
                    {"type": "requestor", "requests": [
                        {"url": TARGET + path, "method": "GET", "responseCode": 200}
                        for path in paths
                    ]},
                    {"type": "activeScan", "parameters": {
                        "context": role, "maxRuleDurationInMins": 1, "maxScanDurationInMins": 8,
                    }},
                    {"type": "passiveScan-wait", "parameters": {"maxDuration": 2}},
                    {"type": "report", "parameters": {
                        "template": "traditional-json", "reportDir": "/zap/reports",
                        "reportFile": f"zap-{role}.json", "reportTitle": "Hemo Connect isolated API DAST",
                    }},
                    {"type": "report", "parameters": {
                        "template": "traditional-html", "reportDir": "/zap/reports",
                        "reportFile": f"zap-{role}.html",
                    }},
                    {"type": "exitStatus", "parameters": {
                        "errorLevel": "High", "okExitValue": 0, "errorExitValue": 1, "warnExitValue": 1,
                    }},
                ],
            }
            (private / f"{role}-plan.yaml").write_text(yaml.safe_dump(plan), encoding="utf-8")
        (private / "redactions.json").write_text(json.dumps(tokens), encoding="utf-8")
    (output / "coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    print(f"DAST preparation passed: {len(coverage)} authenticated read requests; real login and 2FA.")


def sanitize(private: Path, output: Path) -> None:
    tokens = json.loads((private / "redactions.json").read_text(encoding="utf-8"))
    for path in output.glob("zap-*"):
        if path.suffix not in {".json", ".html"}:
            continue
        content = path.read_text(encoding="utf-8")
        for token in tokens:
            content = content.replace(token, "[REDACTED]")
        path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "sanitize"])
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.private, args.output)
    else:
        sanitize(args.private, args.output)
