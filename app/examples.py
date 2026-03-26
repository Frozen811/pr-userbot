"""
Example usage patterns for Telethon userbot with anti-spam features.

This module demonstrates production-ready usage of all components:
- Client initialization with device fingerprints
- Content randomization (anti-hash)
- Human behavior simulation
- Safe error handling
- Timezone-aware scheduling
"""

import asyncio
from app.main import (
    client,
    initialize_client_connection,
    close_client_connection,
    add_chat_to_broadcast,
    send_message_with_anti_spam,
    broadcast_to_chats,
    get_broadcast_stats,
    BROADCAST_CHATS,
    FAILED_CHATS
)
from app.anti_spam import (
    process_spintax,
    uniqualize_text,
    create_message_variations,
    insert_random_emojis
)
from app.human_behavior import HumanBehaviorSimulator
from app import config
import logging

logger = logging.getLogger(__name__)


async def example_broadcast_with_spintax():
    """
    Example 1: Broadcast message with spintax template.
    Text is automatically randomized on each send to evade anti-spam.
    """
    
    await initialize_client_connection()
    
    # Add chats to broadcast list
    await add_chat_to_broadcast(123456789, "Test Chat 1")
    await add_chat_to_broadcast(987654321, "Test Chat 2")
    
    # Message template with spintax
    template = """
    {Привет|Здравствуйте|Добрый день}! 
    Это {сообщение|статья|пост} на {интересную тему|важный вопрос|актуальную проблему}.
    {Рекомендую прочитать|Советую ознакомиться|Предлагаю узнать больше}.
    """
    
    # Broadcast with automatic spintax processing and anti-hash
    stats = await broadcast_to_chats(template, randomize_chat_order=True)
    logger.info(f"Результат: {stats}")
    
    await close_client_connection()


async def example_scheduled_broadcast():
    """
    Example 2: Schedule broadcasts during active hours only (8:00-23:00 Kyiv time).
    """
    
    await initialize_client_connection()
    
    while True:
        # Check night mode before processing
        if await HumanBehaviorSimulator.enforce_night_mode():
            logger.info("🌙 Ночной режим, засыпаю...")
            continue
        
        # Send broadcasts
        template = "Пример рассылки с проверкой расписания"
        await broadcast_to_chats(template)
        
        # Sleep before next cycle
        await HumanBehaviorSimulator.random_delay(3600, 7200)
    
    await close_client_connection()


async def example_safe_single_message():
    """
    Example 3: Send single message to chat with full error handling.
    """
    
    await initialize_client_connection()
    
    chat_id = 123456789
    text = "Сообщение с {автоматической|компьютерной} уникализацией"
    
    success = await send_message_with_anti_spam(client, chat_id, text)
    
    if success:
        logger.info("✅ Сообщение доставлено")
    else:
        logger.warning("❌ Не удалось отправить сообщение")
    
    await close_client_connection()


async def example_gradual_broadcast():
    """
    Example 4: Gradual broadcast with human-like delays and typing simulation.
    """
    
    await initialize_client_connection()
    
    chats = [123456789, 987654321, 555555555]
    template = "Постепенная рассылка с имитацией человеческого поведения"
    
    for i, chat_id in enumerate(chats, 1):
        logger.info(f"Отправка {i}/{len(chats)}")
        
        # Simulate reading before sending
        await HumanBehaviorSimulator.simulate_reading(template)
        
        # Send with anti-spam
        await send_message_with_anti_spam(client, chat_id, template)
        
        # Random delay between messages
        await HumanBehaviorSimulator.random_delay()
    
    logger.info("✅ Рассылка завершена")
    await close_client_connection()


async def example_create_variations():
    """
    Example 5: Create multiple unique variations of the same message.
    Useful for A/B testing or ensuring no hash duplicates.
    """
    
    base_text = "Базовый текст с {вариантом|опцией} для варьирования"
    
    # Generate 5 unique variations
    variations = create_message_variations(base_text, count=5)
    
    for i, variation in enumerate(variations, 1):
        logger.info(f"Вариант {i}: {variation[:50]}...")


async def example_broadcast_statistics():
    """
    Example 6: Track and display broadcast statistics.
    """
    
    await initialize_client_connection()
    
    # After some broadcasts...
    await add_chat_to_broadcast(123456789, "Chat 1")
    await add_chat_to_broadcast(987654321, "Chat 2")
    
    stats = await get_broadcast_stats()
    logger.info(f"📊 Статистика:")
    logger.info(f"   Всего чатов: {stats['total_chats']}")
    logger.info(f"   Ошибок: {stats['failed_chats']}")
    logger.info(f"   Список чатов: {stats['broadcast_chats']}")
    
    await close_client_connection()


async def example_content_randomization():
    """
    Example 7: Demonstrate content randomization techniques.
    """
    
    text = "Демонстрация {техники|метода} рандомизации {содержимого|текста}"
    
    # Apply full randomization
    randomized = uniqualize_text(text, apply_spintax=True, add_emojis=True, 
                                 add_zero_width=True, randomize_structure=True)
    logger.info(f"Исходный текст: {text}")
    logger.info(f"Рандомизированный: {randomized}")
    
    # Process spintax only
    spintax_result = process_spintax(text)
    logger.info(f"С обработкой spintax: {spintax_result}")


async def example_multi_template_broadcast():
    """
    Example 8: Broadcast different templates to different chat groups.
    """
    
    await initialize_client_connection()
    
    chats_group1 = [123456789, 111111111]
    chats_group2 = [987654321, 222222222]
    
    template1 = "Шаблон для {первой|1-й} {группы|категории}"
    template2 = "Альтернативный шаблон для {второй|2-й} {группы|категории}"
    
    # Broadcast to group 1
    for chat_id in chats_group1:
        await add_chat_to_broadcast(chat_id)
    
    logger.info("📬 Рассылка группе 1...")
    stats1 = await broadcast_to_chats(template1)
    
    BROADCAST_CHATS.clear()
    
    # Broadcast to group 2
    for chat_id in chats_group2:
        await add_chat_to_broadcast(chat_id)
    
    logger.info("📬 Рассылка группе 2...")
    stats2 = await broadcast_to_chats(template2)
    
    logger.info(f"Результат группы 1: {stats1}")
    logger.info(f"Результат группы 2: {stats2}")
    
    await close_client_connection()


async def example_error_recovery():
    """
    Example 9: Demonstrate automatic error recovery and retry logic.
    
    The error handling is automatic in send_message_with_anti_spam:
    - FloodWait: Automatic sleep with extra buffer
    - PeerFlood: Remove from list and continue
    - Ban/Restrict: Permanent removal from list
    """
    
    await initialize_client_connection()
    
    chat_id = 123456789
    text = "Сообщение с {автоматической|встроенной} обработкой ошибок"
    
    # This function handles all errors internally
    success = await send_message_with_anti_spam(client, chat_id, text)
    
    if not success:
        logger.warning(f"Чат {chat_id} был исключен из-за ошибки")
    
    await close_client_connection()


# --- Integration with config ---
logger.info(f"Параметры бота:")
logger.info(f"  Устройство: {config.DEVICE_MODEL}")
logger.info(f"  ОС: {config.SYSTEM_VERSION}")
logger.info(f"  Версия приложения: {config.APP_VERSION}")
logger.info(f"  Язык: {config.LANG_CODE}")
logger.info(f"  Часовой пояс: {config.TIMEZONE}")
logger.info(f"  Ночной режим: {config.NIGHT_MODE_START}:00 - {config.NIGHT_MODE_END}:00")
logger.info(f"  Задержка между сообщениями: {config.MIN_DELAY}s - {config.MAX_DELAY}s")


if __name__ == "__main__":
    # Run an example (uncomment desired example)
    # asyncio.run(example_broadcast_with_spintax())
    # asyncio.run(example_scheduled_broadcast())
    # asyncio.run(example_safe_single_message())
    # asyncio.run(example_gradual_broadcast())
    # asyncio.run(example_create_variations())
    # asyncio.run(example_broadcast_statistics())
    # asyncio.run(example_content_randomization())
    # asyncio.run(example_multi_template_broadcast())
    # asyncio.run(example_error_recovery())
    pass
