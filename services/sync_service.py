import httpx
import logging
from core.config import config
from core.security import security_manager

logger = logging.getLogger(__name__)

class SyncService:
    def __init__(self):
        self.headers = {
            "X-Gateway-Token": config.API_TOKEN,
            "Authorization": f"Bearer {config.API_TOKEN}"
        }
        
    async def push_encrypted_data(self, endpoint: str, data: dict):
        """Encrypts data locally and pushes it to the Cloud Backup."""
        if not config.API_TOKEN:
            logger.warning("No API_TOKEN configured. Skipping push.")
            return False
            
        try:
            encrypted_payload = security_manager.encrypt_data(data)
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{config.CLOUD_URL}/{endpoint}",
                    json={"payload": encrypted_payload},
                    headers=self.headers,
                    timeout=30.0
                )
                
            if response.status_code == 200:
                logger.info("Data pushed to cloud successfully.")
                return True
            else:
                logger.error(f"Failed to push data: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Exception pushing data to cloud: {e}")
            return False

    async def pull_encrypted_data(self, endpoint: str) -> dict:
        """Pulls encrypted data from the Cloud and decrypts it locally."""
        if not config.API_TOKEN:
            logger.warning("No API_TOKEN configured. Skipping pull.")
            return None
            
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{config.CLOUD_URL}/{endpoint}",
                    headers=self.headers,
                    timeout=30.0
                )
                
            if response.status_code == 200:
                json_data = response.json()
                if "payload" in json_data:
                    decrypted_data = security_manager.decrypt_data(json_data["payload"])
                    logger.info("Data pulled and decrypted successfully.")
                    return decrypted_data
                return json_data
            else:
                logger.error(f"Failed to pull data: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Exception pulling data from cloud: {e}")
            return None

    async def push_data(self, endpoint: str, data: dict) -> bool:
        """Pushes data unencrypted to the Cloud securely over HTTPS."""
        if not config.API_TOKEN:
            logger.warning("No API_TOKEN configured. Skipping push.")
            return False
            
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{config.CLOUD_URL}/{endpoint}",
                    json=data,
                    headers=self.headers,
                    timeout=30.0
                )
                
            if response.status_code in (200, 201):
                logger.info("Data pushed to cloud successfully.")
                return True
            else:
                logger.error(f"Failed to push data: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Exception pushing data to cloud: {e}")
            return False

sync_service = SyncService()
