import logging


logger = logging.getLogger("app.audit")


def registrar_evento(
    acao: str,
    status: str,
    *,
    ator: str | None = None,
    motivo: str | None = None,
) -> None:
    """Registra eventos operacionais em formato estável, sem incluir segredos."""
    campos = [f"acao={acao}", f"status={status}"]
    if ator:
        campos.append(f"ator={ator}")
    if motivo:
        campos.append(f"motivo={motivo}")

    mensagem = "AUDIT | " + " | ".join(campos)
    if status in {"falha", "bloqueado"}:
        logger.warning(mensagem)
    else:
        logger.info(mensagem)
