"""
Safe API error handler.
Handles FloodWait, PeerFlood, and other Telegram API errors gracefully.
"""

import asyncio
import random
import logging
from typing import Optional, Callable

from telethon import errors as tg_errors

from app import config

logger = logging.getLogger(__name__)

FloodWaitError = tg_errors.FloodWaitError
PeerFloodError = getattr(tg_errors, "PeerFloodError", tg_errors.RPCError)
ChatWriteForbiddenError = getattr(tg_errors, "ChatWriteForbiddenError", tg_errors.RPCError)
UserBannedInChannelError = getattr(tg_errors, "UserBannedInChannelError", tg_errors.RPCError)
ChatAdminRequiredError = getattr(tg_errors, "ChatAdminRequiredError", tg_errors.RPCError)
ChannelPrivateError = getattr(tg_errors, "ChannelPrivateError", tg_errors.RPCError)
ChannelInvalidError = getattr(tg_errors, "ChannelInvalidError", tg_errors.RPCError)
ChatIdInvalidError = getattr(tg_errors, "ChatIdInvalidError", tg_errors.RPCError)
ChatInvalidError = getattr(tg_errors, "ChatInvalidError", tg_errors.RPCError)
UserNotParticipantError = getattr(tg_errors, "UserNotParticipantError", tg_errors.RPCError)
PeerIdInvalidError = getattr(tg_errors, "PeerIdInvalidError", tg_errors.RPCError)


class TelegramErrorHandler:
    """Handles Telegram API errors with appropriate strategies."""
    
    RECOVERABLE_ERRORS = (FloodWaitError, PeerFloodError, ChatAdminRequiredError)
    NON_RECOVERABLE_ERRORS = (
        ChatWriteForbiddenError,
        UserBannedInChannelError,
        ChannelPrivateError,
        ChannelInvalidError,
        ChatIdInvalidError,
        ChatInvalidError,
        UserNotParticipantError,
        PeerIdInvalidError,
    )
    
    ERROR_MESSAGES = {
        FloodWaitError: "FloodWait",
        PeerFloodError: "PeerFlood",
        ChatWriteForbiddenError: "ChatWriteForbidden",
        UserBannedInChannelError: "UserBannedInChannel",
        ChatAdminRequiredError: "ChatRestricted",
        ChannelPrivateError: "ChannelPrivate",
        ChatIdInvalidError: "ChatIdInvalid",
        ChatInvalidError: "ChatInvalid",
    }
    
    @staticmethod
    async def _sleep_with_segments(total_seconds: int):
        """Sleeps with periodic status updates."""
        segments = max(1, total_seconds // 10)
        segment_duration = total_seconds / segments
        
        for segment in range(segments):
            await asyncio.sleep(segment_duration)
            remaining = total_seconds - (segment * segment_duration)
            if remaining > 0:
                logger.debug(f"Sleep: {remaining:.1f}s remaining")
    
    @staticmethod
    async def handle_floodwait(wait_time: int, callback: Optional[Callable] = None) -> None:
        """Handles FloodWait with exponential backoff."""
        multiplied_wait = int(wait_time * config.FLOODWAIT_BASE_MULTIPLIER)
        extra_sleep = random.randint(
            config.FLOODWAIT_EXTRA_SLEEP_MIN,
            config.FLOODWAIT_EXTRA_SLEEP_MAX
        )
        total_wait = multiplied_wait + extra_sleep
        
        logger.warning(f"FloodWait {wait_time}s → sleeping {total_wait}s")
        await TelegramErrorHandler._sleep_with_segments(total_wait)
        
        if callback:
            await callback()
    
    @staticmethod
    async def _handle_permanent_error(error_name: str, chat_id: int,
                                     callback: Optional[Callable] = None) -> None:
        """Handles permanent errors by removing chat."""
        logger.warning(f"{error_name} in chat {chat_id}: removing")
        if callback:
            await callback(chat_id)
    
    @staticmethod
    async def handle_error(error: Exception, chat_id: Optional[int] = None,
                          remove_callback: Optional[Callable] = None,
                          retry_callback: Optional[Callable] = None) -> bool:
        """Universal error handler routing to specific handlers."""
        error_type = type(error)
        
        if isinstance(error, FloodWaitError):
            wait_time = int(getattr(error, "seconds", getattr(error, "value", 0) or 0))
            await TelegramErrorHandler.handle_floodwait(wait_time, retry_callback)
            return True
        
        if isinstance(error, PeerFloodError) and chat_id:
            await TelegramErrorHandler._handle_permanent_error("PeerFlood", chat_id, remove_callback)
            return True
        
        if isinstance(error, TelegramErrorHandler.NON_RECOVERABLE_ERRORS) and chat_id:
            error_name = TelegramErrorHandler.ERROR_MESSAGES.get(error_type, type(error).__name__)
            await TelegramErrorHandler._handle_permanent_error(error_name, chat_id, remove_callback)
            return False
        
        logger.error(f"Unhandled {type(error).__name__}: {str(error)}")
        return False
    
    @staticmethod
    def is_permanent_error(error: Exception) -> bool:
        """Checks if error is permanent."""
        return isinstance(error, TelegramErrorHandler.NON_RECOVERABLE_ERRORS)
    
    @staticmethod
    def is_recoverable_error(error: Exception) -> bool:
        """Checks if error can be recovered."""
        return isinstance(error, TelegramErrorHandler.RECOVERABLE_ERRORS)
