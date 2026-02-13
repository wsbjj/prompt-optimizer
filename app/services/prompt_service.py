import logging
from app.core.llm import LLMClient
from app.core.prompts import PROMPTS, PromptTemplate
from app.schemas.prompt import OptimizeType
import json

logger = logging.getLogger(__name__)

class PromptService:
    def __init__(self):
        self.llm_client = LLMClient()

    async def analyze_need_for_clarification(self, prompt: str) -> dict:
        """
        分析是否需要澄清
        返回: 
        {
            "needs_clarification": bool,
            "questions": List[str], # if True
            "reason": str # if True
        }
        """
        template = PROMPTS[PromptTemplate.CLARIFICATION_CHECK]
        system_prompt = template.replace("{{originalPrompt}}", prompt)
        
        messages = [
            {"role": "user", "content": system_prompt}
        ]
        
        try:
            response = await self.llm_client.chat(messages, temperature=0.5)
            response = response.strip()
            
            if "NO_QUESTIONS" in response:
                return {"needs_clarification": False}
            
            # 尝试解析 JSON
            try:
                # 某些模型可能包含 ```json ... ```，需要清理
                if "```" in response:
                    response = response.split("```")[1]
                    if response.startswith("json"):
                        response = response[4:]
                
                data = json.loads(response)
                return {
                    "needs_clarification": True,
                    "questions": data.get("questions", []),
                    "reason": data.get("reason", "")
                }
            except Exception as e:
                logger.warning(f"Failed to parse clarification JSON: {response}")
                # Fallback
                return {"needs_clarification": False}
                
        except Exception as e:
            logger.error(f"Failed to analyze clarification: {e}")
            return {"needs_clarification": False}

    async def optimize(self, prompt: str, optimize_type: OptimizeType, context: str = None) -> str:
        """
        根据指定类型优化给定的提示词。
        """
        if context:
            # 如果有上下文（用户回答），使用上下文模板
            template = PROMPTS[PromptTemplate.OPTIMIZE_WITH_CONTEXT]
            system_prompt = template.replace("{{originalPrompt}}", prompt).replace("{{clarificationContext}}", context)
        elif optimize_type == OptimizeType.SYSTEM:
            template = PROMPTS[PromptTemplate.ANALYTICAL]
            system_prompt = template.replace("{{originalPrompt}}", prompt)
        elif optimize_type == OptimizeType.USER_BASIC:
            template = PROMPTS[PromptTemplate.USER_BASIC]
            system_prompt = template.replace("{{originalPrompt}}", prompt)
        elif optimize_type == OptimizeType.USER_PROFESSIONAL:
            template = PROMPTS[PromptTemplate.USER_PROFESSIONAL]
            system_prompt = template.replace("{{originalPrompt}}", prompt)
        elif optimize_type == OptimizeType.ITERATE:
            template = PROMPTS[PromptTemplate.ITERATE]
            system_prompt = template.replace("{{originalPrompt}}", prompt)
        elif optimize_type == OptimizeType.IMAGE:
            template = PROMPTS[PromptTemplate.IMAGE_OPTIMIZATION]
            system_prompt = template.replace("{{originalPrompt}}", prompt)
        elif optimize_type == OptimizeType.REPORT:
            # Report mode uses current date as extra formatting arg
            import datetime
            current_date = datetime.datetime.now().strftime("%Y-%m-%d")
            template = PROMPTS[PromptTemplate.REPORT_OPTIMIZATION]
            system_prompt = template.format(user_input=prompt, current_date=current_date)
        else:
            # 默认回退
            template = PROMPTS[PromptTemplate.USER_BASIC]
            system_prompt = template.replace("{{originalPrompt}}", prompt)

        # 构建 LLM 消息
        messages = [
            {"role": "system", "content": "You are a helpful assistant specialized in prompt engineering."},
            {"role": "user", "content": system_prompt}
        ]

        try:
            optimized_content = await self.llm_client.chat(messages)
            return optimized_content
        except Exception as e:
            logger.error(f"Failed to optimize prompt: {e}")
            raise e
            
    async def optimize_stream(self, prompt: str, optimize_type: OptimizeType, context: str = None):
        """
        流式优化提示词 (Generator)
        """
        if context:
            # 如果有上下文（用户回答），使用上下文模板
            template = PROMPTS[PromptTemplate.OPTIMIZE_WITH_CONTEXT]
            system_prompt = template.replace("{{originalPrompt}}", prompt).replace("{{clarificationContext}}", context)
        elif optimize_type == OptimizeType.SYSTEM:
            template = PROMPTS[PromptTemplate.ANALYTICAL]
            system_prompt = template.replace("{{originalPrompt}}", prompt)
        elif optimize_type == OptimizeType.USER_BASIC:
            template = PROMPTS[PromptTemplate.USER_BASIC]
            system_prompt = template.replace("{{originalPrompt}}", prompt)
        elif optimize_type == OptimizeType.USER_PROFESSIONAL:
            template = PROMPTS[PromptTemplate.USER_PROFESSIONAL]
            system_prompt = template.replace("{{originalPrompt}}", prompt)
        elif optimize_type == OptimizeType.ITERATE:
            template = PROMPTS[PromptTemplate.ITERATE]
            system_prompt = template.replace("{{originalPrompt}}", prompt)
        elif optimize_type == OptimizeType.IMAGE:
            template = PROMPTS[PromptTemplate.IMAGE_OPTIMIZATION]
            system_prompt = template.replace("{{originalPrompt}}", prompt)
        elif optimize_type == OptimizeType.REPORT:
            # Report mode uses current date as extra formatting arg
            import datetime
            current_date = datetime.datetime.now().strftime("%Y-%m-%d")
            template = PROMPTS[PromptTemplate.REPORT_OPTIMIZATION]
            system_prompt = template.format(user_input=prompt, current_date=current_date)
        else:
            # 默认回退
            template = PROMPTS[PromptTemplate.USER_BASIC]
            system_prompt = template.replace("{{originalPrompt}}", prompt)

        messages = [
            {"role": "system", "content": "You are a helpful assistant specialized in prompt engineering."},
            {"role": "user", "content": system_prompt}
        ]
        
        async for chunk in self.llm_client.chat_stream(messages):
            yield chunk

    async def analyze_image(self, image_data: bytes) -> str:
        """
        使用视觉模型分析图片内容
        """
        prompt = "请详细描述这张图片的内容，包括画面主体、环境背景、色彩光影、构图方式以及画面传达的氛围或情绪。请用通俗易懂的语言描述。"
        try:
            return await self.llm_client.chat_with_image(prompt, image_data)
        except Exception as e:
            logger.error(f"Failed to analyze image: {e}")
            raise e

    async def analyze_image_stream(self, image_data: bytes):
        """
        使用视觉模型分析图片内容 (流式)
        """
        prompt = "请详细描述这张图片的内容，包括画面主体、环境背景、色彩光影、构图方式以及画面传达的氛围或情绪。请用通俗易懂的语言描述。"
        async for chunk in self.llm_client.chat_with_image_stream(prompt, image_data):
            yield chunk

    async def optimize_with_image(self, user_instruction: str, image_description: str) -> str:
        """
        结合图片语义理解和用户指令进行提示词优化
        """
        # 构造组合输入
        combined_input = f"""【参考图片画面信息】：
{image_description}

【用户原始指令】：
{user_instruction}

【优化目标】：
请参考上述图片的画面信息，结合用户指令，应用“欧美写实·产品场景化”生成逻辑 (Golden Prompt Formula)，生成一张极具商业转化潜力的摄影级提示词。"""
        
        # 使用 IMAGE 模板进行优化
        return await self.optimize(combined_input, OptimizeType.IMAGE)

    async def optimize_with_image_stream(self, user_instruction: str, image_description: str):
        """
        结合图片语义理解和用户指令进行提示词优化 (流式)
        """
        # 构造组合输入
        combined_input = f"""【参考图片画面信息】：
{image_description}

【用户原始指令】：
{user_instruction}

【优化目标】：
请参考上述图片的画面信息，结合用户指令，应用“欧美写实·产品场景化”生成逻辑 (Golden Prompt Formula)，生成一张极具商业转化潜力的摄影级提示词。"""
        
        # 使用 IMAGE 模板进行流式优化
        async for chunk in self.optimize_stream(combined_input, OptimizeType.IMAGE):
            yield chunk

    async def analyze_image_mode_intent(self, text: str) -> str:
        """
        分析用户在图片模式下的纯文字输入意图
        """
        prompt = f"""User input in Image Mode (without image uploaded): "{text}"
Analyze the intent:
1. GEN_IMAGE: User provides a visual description wanting image prompts (e.g., "A modern living room...", "一只猫").
2. FORCE_TEXT: User explicitly requests to proceed without image or skip upload (e.g., "直接优化", "不传图了", "就用这段文字").
3. OTHER: Chit-chat or irrelevant (e.g., "你好", "在吗").

Return ONLY the code (GEN_IMAGE, FORCE_TEXT, or OTHER)."""

        try:
            response = await self.llm_client.chat_simple(prompt)
            intent = response.strip().upper()
            if "GEN_IMAGE" in intent: return "GEN_IMAGE"
            if "FORCE_TEXT" in intent: return "FORCE_TEXT"
            return "OTHER"
        except Exception as e:
            logger.error(f"Failed to analyze intent: {e}")
            return "OTHER"

prompt_service = PromptService()
