import asyncio
import qrcode
from telethon.errors import SessionPasswordNeededError
from app.client_manager import ClientManager

async def main():
    client = ClientManager.create_client()
    await client.connect()
    
    qr = await client.qr_login()
    
    print("Отсканируйте QR-код в Telegram:")
    qr_img = qrcode.QRCode()
    qr_img.add_data(qr.url)
    qr_img.print_ascii(invert=True)
    
    print("Ожидание подтверждения авторизации...")
    
    try:
        await qr.wait()
        print(">>> УРА! Сессия успешно создана!")
    except SessionPasswordNeededError:
        password = input(">>> Обнаружена двухэтапная аутентификация! Введите пароль: ")
        await client.sign_in(password=password)
        print(">>> УРА! Пароль принят, сессия успешно создана!")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())