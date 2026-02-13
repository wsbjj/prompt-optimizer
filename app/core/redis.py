import logging
from typing import Optional
import redis.asyncio as redis
from app.core.config import settings

logger = logging.getLogger(__name__)

class StateManager:
    """
    状态管理器 (Redis 实现)
    """
    _instance = None
    
    # 默认过期时间 10 分钟 (600秒)
    DEFAULT_TTL = 600

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StateManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        # 初始化 Redis 连接池
        self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        self._initialized = True
        logger.info(f"StateManager initialized with Redis: {settings.REDIS_URL}")

    async def set_user_mode(self, user_id: str, mode: str, ttl: int = DEFAULT_TTL):
        """
        设置用户模式
        :param user_id: 用户 ID
        :param mode: 模式 Key
        :param ttl: 过期时间 (秒)
        """
        try:
            await self.redis.set(user_id, mode, ex=ttl)
            logger.debug(f"Set user mode (Redis): {user_id} -> {mode}")
        except Exception as e:
            logger.error(f"Failed to set user mode in Redis: {e}")

    async def get_user_mode(self, user_id: str) -> Optional[str]:
        """
        获取用户模式
        """
        try:
            mode = await self.redis.get(user_id)
            return mode
        except Exception as e:
            logger.error(f"Failed to get user mode from Redis: {e}")
            return None

    async def clear_user_mode(self, user_id: str):
        """
        清除用户模式
        """
        try:
            await self.redis.delete(user_id)
            logger.debug(f"Cleared user mode (Redis): {user_id}")
        except Exception as e:
            logger.error(f"Failed to clear user mode in Redis: {e}")

    async def set_value(self, key: str, value: str, ttl: int = DEFAULT_TTL):
        """
        设置通用键值对
        """
        try:
            await self.redis.set(key, value, ex=ttl)
            logger.debug(f"Set value (Redis): {key} -> {value[:20]}...")
        except Exception as e:
            logger.error(f"Failed to set value in Redis: {e}")

    async def get_value(self, key: str) -> Optional[str]:
        """
        获取通用键值对
        """
        try:
            return await self.redis.get(key)
        except Exception as e:
            logger.error(f"Failed to get value from Redis: {e}")
            return None

    async def delete_value(self, key: str):
        """
        删除通用键值对
        """
        try:
            await self.redis.delete(key)
            logger.debug(f"Deleted value (Redis): {key}")
        except Exception as e:
            logger.error(f"Failed to delete value in Redis: {e}")

    async def close(self):
        """
        关闭 Redis 连接
        """
        await self.redis.close()

state_manager = StateManager()
