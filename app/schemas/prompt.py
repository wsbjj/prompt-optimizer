from enum import Enum
from pydantic import BaseModel
from typing import Optional

class OptimizeType(str, Enum):
    SYSTEM = "system"
    USER_BASIC = "user_basic"
    USER_PROFESSIONAL = "user_professional"
    ITERATE = "iterate"
    IMAGE = "image"
    REPORT = "report"

class PromptOptimizeRequest(BaseModel):
    prompt: str
    type: OptimizeType = OptimizeType.USER_BASIC
    conversation_id: Optional[str] = None

class PromptOptimizeResponse(BaseModel):
    optimized_prompt: str
    original_prompt: str
    type: OptimizeType
