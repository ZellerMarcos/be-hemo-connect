import argparse
import ipaddress
from pathlib import Path

import uvicorn
from starlette.types import ASGIApp, Receive, Scope, Send
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


# Preencher somente apos comprovar os peers e a sanitizacao de headers no deploy.
# Vazio deliberadamente: sem prova da topologia, nao habilitar controle por IP em producao.
TRUSTED_PROXY_PEERS: tuple[str, ...] = ()


class DeploymentProxyHeaders(ProxyHeadersMiddleware):
    def __init__(self, app: ASGIApp, trusted_hosts: tuple[str, ...]):
        # Aceita so IPs individuais; wildcard/CIDR ampliariam a fronteira de confianca.
        peers = [str(ipaddress.ip_address(host)) for host in trusted_hosts]
        super().__init__(app, trusted_hosts=peers)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in {"http", "websocket"}:
            scope = dict(scope)
            peer = scope.get("client")
            host = peer[0] if peer else None
            # Guarda a origem da conexao antes de o Uvicorn normalizar scope["client"].
            # A aplicacao usa esta marca, nunca um header externo, para comprovar o proxy.
            scope["state"] = {
                **scope.get("state", {}),
                "verified_proxy_peer": host if host in self.trusted_hosts else None,
            }
        await super().__call__(scope, receive, send)


def create_app() -> ASGIApp:
    from app.main import app

    return DeploymentProxyHeaders(app, TRUSTED_PROXY_PEERS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    uvicorn.run(
        "scripts.serve:create_app",
        factory=True,
        app_dir=str(Path(__file__).resolve().parents[1]),
        host="0.0.0.0",
        port=args.port,
        workers=args.workers,
        # O wrapper da factory ja normaliza headers; nao aplicar a regra duas vezes.
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
