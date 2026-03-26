"""
Telethon client manager.
Handles client initialization with official client fingerprints.
"""

import os
from telethon import TelegramClient

from app import config


class ClientManager:
    """Manages Telethon client initialization with anti-detection fingerprints."""
    
    @staticmethod
    def create_client() -> TelegramClient:
        """Creates and configures Telethon client with device fingerprints."""
        os.makedirs(config.SESSION_DIR, exist_ok=True)

        return TelegramClient(
            session=config.SESSION_PATH,
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            device_model=config.DEVICE_MODEL,
            system_version=config.SYSTEM_VERSION,
            app_version=config.APP_VERSION,
            lang_code=config.LANG_CODE,
            system_lang_code=config.SYSTEM_LANG_CODE,
        )
    
    @staticmethod
    async def initialize_client(client):
        """Initializes and connects the client."""
        try:
            if not client.is_connected():
                await client.connect()
            return True
        except Exception as e:
            print(f"Failed to connect client: {e}")
            return False
    
    @staticmethod
    async def authenticate_client(client):
        """Authenticates the client (login)."""
        try:
            if not await client.is_user_authorized():
                await client.start(
                    phone=config.PHONE_NUMBER or None,
                    password=config.PASSWORD or None,
                )
            return True
        except Exception as e:
            print(f"Failed to authenticate client: {e}")
            return False
