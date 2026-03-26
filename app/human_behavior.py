"""
Human behavior simulation module.
Implements realistic delays, typing indicators, and activity patterns.
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional

import pytz
from pyrogram import Client
from pyrogram.types import ChatAction

from app import config


def _get_default_param(value, default):
    """Helper to get default parameter value."""
    return value if value is not None else default


def _get_tz(tz_name: str = config.TIMEZONE):
    """Helper to get timezone object."""
    return pytz.timezone(tz_name)


class HumanBehaviorSimulator:
    """Simulates human-like behavior patterns to evade bot detection."""
    
    @staticmethod
    async def random_delay(min_delay: float = None, max_delay: float = None):
        """Applies random delay within bounds."""
        min_delay = _get_default_param(min_delay, config.MIN_DELAY)
        max_delay = _get_default_param(max_delay, config.MAX_DELAY)
        await asyncio.sleep(random.uniform(min_delay, max_delay))
    
    @staticmethod
    async def simulate_typing(client: Client, chat_id: int, text: str, typing_speed_wpm: int = None):
        """Sends typing indicator with duration based on text length."""
        typing_speed_wpm = _get_default_param(typing_speed_wpm, config.TYPING_SPEED_WPM)
        
        word_count = len(text.split())
        typing_duration = (word_count / typing_speed_wpm) * 60
        typing_duration = max(1.0, min(typing_duration, 30.0))
        
        try:
            await client.send_chat_action(chat_id, ChatAction.TYPING)
            
            typing_segments = max(1, int(typing_duration / 5))
            segment_duration = typing_duration / typing_segments
            
            for _ in range(typing_segments):
                await asyncio.sleep(segment_duration)
                await client.send_chat_action(chat_id, ChatAction.TYPING)
        except Exception:
            pass
    
    @staticmethod
    async def simulate_reading(text: str):
        """Simulates reading delay before response."""
        word_count = len(text.split())
        reading_duration = random.uniform(config.MIN_READING_DELAY, config.MAX_READING_DELAY)
        adjusted_duration = reading_duration + (word_count * 0.1)
        adjusted_duration = max(config.MIN_READING_DELAY, min(adjusted_duration, 15.0))
        
        await asyncio.sleep(adjusted_duration)
    
    @staticmethod
    async def simulate_activity(client: Client, chat_id: int):
        """Simulates general account activity."""
        try:
            actions = [ChatAction.TYPING, ChatAction.RECORD_VIDEO, ChatAction.RECORD_AUDIO]
            await client.send_chat_action(chat_id, random.choice(actions))
            await asyncio.sleep(random.uniform(1, 3))
        except Exception:
            pass
    
    @staticmethod
    async def sleep_after_broadcast(min_sleep: int = None, max_sleep: int = None):
        """Long sleep after broadcast completion."""
        min_sleep = _get_default_param(min_sleep, config.SLEEP_AFTER_BROADCAST_MIN)
        max_sleep = _get_default_param(max_sleep, config.SLEEP_AFTER_BROADCAST_MAX)
        await asyncio.sleep(random.randint(min_sleep, max_sleep))
    
    @staticmethod
    def is_night_time(tz_name: str = config.TIMEZONE) -> bool:
        """Checks if current time is in night mode hours."""
        tz = _get_tz(tz_name)
        current_hour = datetime.now(tz).hour
        return config.NIGHT_MODE_START <= current_hour or current_hour < config.NIGHT_MODE_END
    
    @staticmethod
    async def sleep_until_morning(tz_name: str = config.TIMEZONE):
        """Sleeps until morning with random offset."""
        tz = _get_tz(tz_name)
        now = datetime.now(tz)
        
        offset_minutes = random.randint(config.NIGHT_MODE_OFFSET_MIN, config.NIGHT_MODE_OFFSET_MAX)
        wake_time = now.replace(hour=config.NIGHT_MODE_END, minute=offset_minutes, second=0)
        
        if now.hour < config.NIGHT_MODE_END:
            wake_time += timedelta(days=1)
        
        sleep_seconds = max(0, (wake_time - now).total_seconds())
        if sleep_seconds > 0:
            await asyncio.sleep(sleep_seconds)
    
    @staticmethod
    async def enforce_night_mode(tz_name: str = config.TIMEZONE, client: Optional[Client] = None) -> bool:
        """Enforces night mode sleep if needed."""
        if HumanBehaviorSimulator.is_night_time(tz_name):
            stopped_for_night = False
            if client is not None and client.is_connected:
                await client.stop()
                stopped_for_night = True

            await HumanBehaviorSimulator.sleep_until_morning(tz_name)

            if client is not None and stopped_for_night and not client.is_connected:
                await client.start()
            return True
        return False
    
    @staticmethod
    async def wait_until_wake_time(tz_name: str = config.TIMEZONE):
        """Waits until active hours."""
        while True:
            if not HumanBehaviorSimulator.is_night_time(tz_name):
                break
            await HumanBehaviorSimulator.sleep_until_morning(tz_name)
            await asyncio.sleep(60)
    
    @staticmethod
    async def simulate_pre_send_activity(client: Client, chat_id: int, text: str):
        """Pre-send activity: reading + typing."""
        await HumanBehaviorSimulator.simulate_reading(text)
        await HumanBehaviorSimulator.simulate_typing(client, chat_id, text)
