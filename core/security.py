import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from core.config import config
import json

class SecurityManager:
    def __init__(self):
        # Derive a secure key from the environment secret
        salt = b'hipocrafy_edge_salt'
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(config.ENCRYPTION_KEY.encode()))
        self.fernet = Fernet(key)

    def encrypt_data(self, data: dict) -> str:
        """Encrypts a dictionary to a secure base64 string."""
        json_data = json.dumps(data)
        return self.fernet.encrypt(json_data.encode()).decode()

    def decrypt_data(self, encrypted_string: str) -> dict:
        """Decrypts a secure base64 string back to a dictionary."""
        decrypted_data = self.fernet.decrypt(encrypted_string.encode()).decode()
        return json.loads(decrypted_data)

security_manager = SecurityManager()
