import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from app.client_manager import ClientManager

client = ClientManager.create_client()

print("🔍 Локальная проверка отпечатков клиента...")
print(f"API ID: {client.api_id}")
print(f"Device Model: {client.device_model}")
print(f"System Version: {client.system_version}")
print(f"App Version: {client.app_version}")
print(f"System Lang: {getattr(client, 'system_lang_code', 'not supported by this Pyrogram version')}")
print(f"Proxy: {client.proxy}")