import logging
import base64
from typing import Optional, List, Dict, Any
from openai import AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)

class LLMClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        api_key = settings.OPENAI_API_KEY
        base_url = settings.OPENAI_BASE_URL
        self.model = settings.OPENAI_MODEL
        self.vl_model = settings.SILICONFLOW_VL_MODEL
        
        if not api_key:
            logger.warning("OPENAI_API_KEY not found in settings")
            
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        self._initialized = True

    async def chat(self, 
                   messages: List[Dict[str, str]], 
                   temperature: float = 0.7,
                   max_tokens: int = 2000,
                   model: str = None) -> str:
        """
        向 LLM 发送聊天补全请求
        """
        try:
            target_model = model or self.model
            logger.info(f"Calling LLM: {target_model}")
            response = await self.client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM call failed: {str(e)}")
            raise e

    async def chat_with_image(self, 
                            prompt: str, 
                            image_data: bytes, 
                            temperature: float = 0.7,
                            max_tokens: int = 2000) -> str:
        """
        发送带图片的请求到视觉模型
        """
        try:
            # 将图片转换为 Base64
            base64_image = base64.b64encode(image_data).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{base64_image}"

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]

            logger.info(f"Calling VL LLM: {self.vl_model}")
            response = await self.client.chat.completions.create(
                model=self.vl_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"VL LLM call failed: {str(e)}")
            raise e

    async def chat_with_image_stream(self, 
                            prompt: str, 
                            image_data: bytes, 
                            temperature: float = 0.7,
                            max_tokens: int = 2000):
        """
        发送带图片的请求到视觉模型 (Stream 模式)
        """
        try:
            # 将图片转换为 Base64
            base64_image = base64.b64encode(image_data).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{base64_image}"

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]

            logger.info(f"Calling VL LLM (Stream): {self.vl_model}")
            stream = await self.client.chat.completions.create(
                model=self.vl_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"VL LLM stream call failed: {str(e)}")
            raise e

    async def chat_stream(self, 
                   messages: List[Dict[str, str]], 
                   temperature: float = 0.7,
                   max_tokens: int = 2000,
                   model: str = None):
        """
        向 LLM 发送聊天补全请求 (Stream 模式)
        """
        try:
            target_model = model or self.model
            logger.info(f"Calling LLM Stream: {target_model}")
            stream = await self.client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"LLM stream call failed: {str(e)}")
            raise e

    async def chat_simple(self, prompt: str) -> str:
        """
        单轮对话的简单封装
        """
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages)
