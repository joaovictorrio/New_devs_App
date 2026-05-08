"""
Token Access Service
Simple interface for application code to access tokens
Replaces direct environment variable access
"""

import os
from typing import Optional, Dict, Any
from functools import lru_cache
import asyncio
import threading
from app.services.token_manager_simple import get_token_manager
import logging

logger = logging.getLogger(__name__)


def _run_coro_blocking(coro):
    """Run an async coroutine from synchronous code, safely.

    The previous implementation used ``asyncio.create_task(coro).result()``
    which is broken: ``.result()`` on a not-yet-completed Task raises
    ``InvalidStateError`` and you cannot block the running loop on itself.

    Strategy:
        * If we are NOT inside a running event loop, just use ``asyncio.run``.
        * If we ARE inside a running loop, the caller is sync code that
          needs an answer NOW — we run the coroutine on a dedicated worker
          thread (with its own loop) and block this thread waiting for it.
          That keeps the original event loop free.
    """
    try:
        asyncio.get_running_loop()
        running = True
    except RuntimeError:
        running = False

    if not running:
        return asyncio.run(coro)

    # Inside an async context: hand off to a worker thread.
    result_box: Dict[str, Any] = {}
    error_box: Dict[str, Exception] = {}

    def _worker() -> None:
        try:
            result_box["value"] = asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001 - propagated to caller
            error_box["error"] = exc

    t = threading.Thread(target=_worker, name="token-access-sync", daemon=True)
    t.start()
    t.join()
    if "error" in error_box:
        raise error_box["error"]
    return result_box.get("value")

class TokenAccess:
    """
    Service for accessing tokens in application code
    Provides a simple interface similar to environment variables
    """
    
    def __init__(self):
        """Initialize token access service"""
        self._token_manager = get_token_manager()
        self._cache: Dict[str, str] = {}
        self._use_env_fallback = os.getenv('USE_ENV_TOKEN_FALLBACK', 'true').lower() == 'true'
    
    async def get_hostaway_token(self, city: str) -> Optional[str]:
        """
        Get Hostaway API token for a specific city
        
        Args:
            city: City name (london, paris, algiers, lisbon)
            
        Returns:
            Token value or None if not found
        """
        cache_key = f"hostaway_api_{city.lower()}"
        
        # Check cache first
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            # Use the get_token_for_city method for Hostaway tokens
            # This method handles multi-city tokens correctly
            token_data = await self._token_manager.get_token_for_city(
                token_key='hostaway_api',
                city=city.lower(),
                decrypt=True
            )
            
            if token_data and token_data.get('value'):
                self._cache[cache_key] = token_data['value']
                logger.info(f"Successfully retrieved Hostaway token for {city}")
                return token_data['value']
            
        except Exception as e:
            logger.error(f"Failed to get Hostaway token for {city}: {str(e)}")
        
        # Fallback to environment variable if enabled
        if self._use_env_fallback:
            env_key = f"HOSTAWAY_API_{city.upper()}"
            env_value = os.getenv(env_key)
            if env_value:
                logger.info(f"Using environment variable fallback for {env_key}")
                self._cache[cache_key] = env_value
                return env_value
        
        logger.warning(f"No Hostaway token found for city {city}")
        return None
    
    async def get_stripe_secret_key(self) -> Optional[str]:
        """
        Get Stripe secret key
        
        Returns:
            Stripe secret key or None
        """
        return await self._get_token_with_fallback(
            'stripe_secret_key',
            'STRIPE_SECRET_KEY'
        )
    
    async def get_stripe_publishable_key(self) -> Optional[str]:
        """
        Get Stripe publishable key
        
        Returns:
            Stripe publishable key or None
        """
        return await self._get_token_with_fallback(
            'stripe_publishable_key',
            'STRIPE_PUBLISHABLE_KEY'
        )
    
    async def get_stripe_webhook_secret(self) -> Optional[str]:
        """
        Get Stripe webhook secret
        
        Returns:
            Stripe webhook secret or None
        """
        return await self._get_token_with_fallback(
            'stripe_webhook_secret',
            'STRIPE_WEBHOOK_SECRET'
        )
    
    async def get_token(self, purpose: str) -> Optional[str]:
        """
        Get any token by purpose
        
        Args:
            purpose: Token purpose
            
        Returns:
            Token value or None
        """
        # Check cache
        if purpose in self._cache:
            return self._cache[purpose]
        
        try:
            token_data = await self._token_manager.get_token(
                token_key=purpose,
                decrypt=True
            )
            
            if token_data and token_data.get('value'):
                self._cache[purpose] = token_data['value']
                return token_data['value']
                
        except Exception as e:
            logger.error(f"Failed to get token for purpose {purpose}: {str(e)}")
        
        return None
    
    async def _get_token_with_fallback(
        self,
        purpose: str,
        env_key: str
    ) -> Optional[str]:
        """
        Get token with environment variable fallback
        
        Args:
            purpose: Token purpose
            env_key: Environment variable key for fallback
            
        Returns:
            Token value or None
        """
        # Check cache
        if purpose in self._cache:
            return self._cache[purpose]
        
        try:
            # Try database first
            token_data = await self._token_manager.get_token(
                token_key=purpose,
                decrypt=True
            )
            
            if token_data and token_data.get('value'):
                self._cache[purpose] = token_data['value']
                return token_data['value']
                
        except Exception as e:
            logger.error(f"Failed to get token {purpose}: {str(e)}")
        
        # Fallback to environment variable
        if self._use_env_fallback:
            env_value = os.getenv(env_key)
            if env_value:
                logger.info(f"Using environment variable fallback for {env_key}")
                return env_value
        
        return None
    
    def clear_cache(self) -> None:
        """Clear the token cache"""
        self._cache.clear()
    
    def get_all_hostaway_tokens(self) -> Dict[str, str]:
        """
        Get all Hostaway tokens (synchronous wrapper)
        Compatible with existing code

        Returns:
            Dictionary of city -> token mappings
        """
        return _run_coro_blocking(self._get_all_hostaway_tokens_async())
    
    async def _get_all_hostaway_tokens_async(self) -> Dict[str, str]:
        """
        Get all Hostaway tokens asynchronously
        
        Returns:
            Dictionary of city -> token mappings
        """
        cities = ['london', 'paris', 'algiers', 'lisbon']
        tokens = {}
        
        for city in cities:
            token = await self.get_hostaway_token(city)
            if token:
                tokens[f"HOSTAWAY_API_{city.upper()}"] = token
        
        return tokens


# Singleton instance
_token_access: Optional[TokenAccess] = None


def get_token_access() -> TokenAccess:
    """Get or create the singleton token access instance"""
    global _token_access
    if _token_access is None:
        _token_access = TokenAccess()
    return _token_access


# Compatibility layer for existing code
class CompatibleSettings:
    """
    Compatibility layer to replace existing settings usage
    Provides the same interface as the old settings class
    """
    
    def __init__(self):
        self._token_access = get_token_access()
        # Keep original settings for non-token configs
        from app.config import settings as original_settings
        self._original_settings = original_settings
    
    def __getattr__(self, name):
        """Proxy non-token attributes to original settings"""
        return getattr(self._original_settings, name)
    
    def get_hostaway_tokens(self) -> Dict[str, str]:
        """Get all Hostaway tokens (compatible with existing code)"""
        return self._token_access.get_all_hostaway_tokens()
    
    def get_hostaway_token_for_city(self, city: str) -> Optional[str]:
        """Get Hostaway token for specific city (compatible with existing code)"""
        return _run_coro_blocking(self._token_access.get_hostaway_token(city))
    
    @property
    def stripe_secret_key(self) -> Optional[str]:
        """Get Stripe secret key (compatible property)"""
        return _run_coro_blocking(self._token_access.get_stripe_secret_key())

    @property
    def stripe_publishable_key(self) -> Optional[str]:
        """Get Stripe publishable key (compatible property)"""
        return _run_coro_blocking(self._token_access.get_stripe_publishable_key())

    @property
    def stripe_webhook_secret(self) -> Optional[str]:
        """Get Stripe webhook secret (compatible property)"""
        return _run_coro_blocking(self._token_access.get_stripe_webhook_secret())