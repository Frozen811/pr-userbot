import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from app.client_manager import ClientManager
from app import config

client = ClientManager.create_client()

print("Локальная проверка Telethon-конфигурации...")
print(f"API ID: {config.API_ID}")
print(f"API Hash: {config.API_HASH}")
print(f"Device Model: {config.DEVICE_MODEL}")
print(f"System Version: {config.SYSTEM_VERSION}")
print(f"App Version: {config.APP_VERSION}")
print(f"Lang: {config.LANG_CODE}")
print(f"System Lang: {config.SYSTEM_LANG_CODE}")
print(f"Session Path: {config.SESSION_PATH}.session")
print(f"Proxy: {getattr(client, 'proxy', None)}")