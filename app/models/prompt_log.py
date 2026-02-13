from sqlalchemy import Column, Integer, String, Text, DateTime, Enum as SqlEnum
from datetime import datetime
from app.core.database import Base
from app.schemas.prompt import OptimizeType

class PromptLog(Base):
    __tablename__ = "prompt_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)  # 飞书 OpenID
    original_prompt = Column(Text)
    optimized_prompt = Column(Text)
    optimize_type = Column(SqlEnum(OptimizeType))
    created_at = Column(DateTime, default=datetime.utcnow)
