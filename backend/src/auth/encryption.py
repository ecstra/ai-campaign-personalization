import os

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

load_dotenv()

_KEY = os.getenv("TOKEN_ENCRYPTION_KEY")
if not _KEY:
    raise ValueError(
        "TOKEN_ENCRYPTION_KEY environment variable is not set. "
        "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
    )

_fernet = Fernet(_KEY.encode() if isinstance(_KEY, str) else _KEY)


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string using Fernet symmetric encryption."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """
    Decrypt a Fernet-encrypted token string.

    Raises:
        InvalidToken: If the ciphertext is corrupted or the key is wrong.
    """
    return _fernet.decrypt(ciphertext.encode()).decode()
