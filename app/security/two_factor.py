import hashlib
import hmac
import secrets


CODE_LENGTH = 6


def generate_code() -> str:
    # `secrets` evita códigos previsíveis; o preenchimento mantém seis dígitos,
    # inclusive quando o código começa com zero.
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def hash_code(code: str) -> str:
    # O código temporário não precisa ser recuperado, apenas comparado.
    # Este SHA-256 é usado somente para o código 2FA, nunca para senhas.
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def verify_code(code: str, code_hash: str) -> bool:
    # A comparação em tempo constante reduz diferenças observáveis entre
    # tentativas com prefixos coincidentes.
    return hmac.compare_digest(hash_code(code), code_hash)