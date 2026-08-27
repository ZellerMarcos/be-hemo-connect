from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


# Argon2id resiste a ataques com GPU. A biblioteca gera um salt aleatorio
# e unico automaticamente para cada chamada de hash.
password_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Gera e retorna somente o hash Argon2id da senha informada."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Compara uma senha com um hash armazenado sem expor a senha."""
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False