"""
Pyrogram client manager.
Handles client initialization with device fingerprints.
"""

import os
import inspect
from pyrogram import Client

from app import config


class ClientManager:
    """Manages Pyrogram client initialization with anti-detection fingerprints."""
    
    @staticmethod
    def create_client():
        """Creates and configures Pyrogram client with device fingerprints."""
        os.makedirs(config.SESSION_DIR, exist_ok=True)

        client_kwargs = {
            "name": config.SESSION_NAME,
            "api_id": 2040,
            "api_hash": "b18441a1ff607e10a989891a5462e627",
            "phone_number": config.PHONE_NUMBER if config.PHONE_NUMBER else None,
            "workdir": config.SESSION_DIR,
            "device_model": "Lenovo G580",
            "system_version": "Windows 10 x64",
            "app_version": "6.6.2 x64",
            "lang_code": "ru",
            "system_lang_code": "ru-RU",
            "lang_pack": "tdesktop",
        }

        supported_args = set(inspect.signature(Client.__init__).parameters.keys())
        filtered_kwargs = {k: v for k, v in client_kwargs.items() if k in supported_args and v is not None}

        return Client(**filtered_kwargs)
    
    @staticmethod
    async def initialize_client(client):
        """Initializes and connects the client."""
        try:
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
                if config.PASSWORD:
                    await client.start(phone_number=config.PHONE_NUMBER, password=config.PASSWORD)
                else:
                    await client.start(phone_number=config.PHONE_NUMBER)
            return True
        except Exception as e:
            print(f"Failed to authenticate client: {e}")
            return False
