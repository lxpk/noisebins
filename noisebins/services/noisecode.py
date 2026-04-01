import secrets

# URL-safe alphabet without padding; 10 chars (README: 8–12)
_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def generate_noisecode(length: int = 10) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))
