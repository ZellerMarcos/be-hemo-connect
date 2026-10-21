import hashlib
import hmac
import json
import secrets


CODE_LENGTH = 6
VERIFIER_FORMAT = "challenge-secret-v1"


def generate_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def generate_challenge_nonce() -> str:
    return secrets.token_hex(16)


def generate_challenge_secret() -> str:
    # Os 256 bits aleatorios protegem o HMAC mesmo se o banco com codigos curtos vazar.
    return secrets.token_urlsafe(32)


def hash_challenge_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def hash_code(
    code: str,
    *,
    usuario_id: int,
    challenge_nonce: str,
    challenge_secret: str,
) -> str:
    # Dominio, formato e contexto impedem reutilizar o verificador em outro desafio.
    # JSON canonico evita ambiguidades que uma concatenacao de campos permitiria.
    payload = json.dumps(
        ["hemo-connect:2fa", VERIFIER_FORMAT, usuario_id, challenge_nonce, code],
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hmac.new(challenge_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_code(
    code: str,
    code_hash: str,
    *,
    usuario_id: int,
    challenge_nonce: str,
    challenge_secret: str,
) -> bool:
    expected = hash_code(
        code,
        usuario_id=usuario_id,
        challenge_nonce=challenge_nonce,
        challenge_secret=challenge_secret,
    )
    return hmac.compare_digest(expected, code_hash)
