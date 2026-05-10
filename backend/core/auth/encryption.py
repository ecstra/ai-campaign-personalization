import os

from cryptography.fernet import Fernet

_KEY = os.getenv("TOKEN_ENCRYPTION_KEY")
if not _KEY:
    raise ValueError(
        "TOKEN_ENCRYPTION_KEY environment variable is not set. "
        "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
    )

_fernet = Fernet(_KEY.encode())

class EncryptionUtility:

    @staticmethod
    def encrypt_token(plaintext: str) -> str:
        return _fernet.encrypt(plaintext.encode()).decode()

    @staticmethod
    def decrypt_token(ciphertext: str) -> str:
        return _fernet.decrypt(ciphertext.encode()).decode()