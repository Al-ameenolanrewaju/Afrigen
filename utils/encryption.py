import os
import base64
from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken

def _get_fernet() -> Fernet:
    key = os.environ.get("CONNECTED_ACCOUNTS_ENCRYPTION_KEY")
    if not key:
        raise ValueError("CONNECTED_ACCOUNTS_ENCRYPTION_KEY environment variable is not set. This is strictly required for the Connected Accounts infrastructure.")
    # Ensure key is valid base64 32-byte key
    try:
        return Fernet(key.encode('utf-8'))
    except Exception as e:
        raise ValueError(f"CONNECTED_ACCOUNTS_ENCRYPTION_KEY is invalid. It must be a valid Fernet 32-byte url-safe base64-encoded key. Error: {e}")

def encrypt_token(token: str) -> str:
    """Encrypts a plaintext token using Fernet symmetric encryption."""
    if not token:
        return ""
    f = _get_fernet()
    return f.encrypt(token.encode('utf-8')).decode('utf-8')

def decrypt_token(encrypted_token: str) -> str:
    """Decrypts an encrypted token."""
    if not encrypted_token:
        return ""
    f = _get_fernet()
    try:
        return f.decrypt(encrypted_token.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        # In a real system, you might want to log this or raise a specific auth error
        return ""
