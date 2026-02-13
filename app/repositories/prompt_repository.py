from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.prompt_log import PromptLog
from app.schemas.prompt import OptimizeType

class PromptRepository:
    async def create(self, db: AsyncSession, user_id: str, original_prompt: str, optimized_prompt: str, optimize_type: OptimizeType) -> PromptLog:
        db_log = PromptLog(
            user_id=user_id,
            original_prompt=original_prompt,
            optimized_prompt=optimized_prompt,
            optimize_type=optimize_type
        )
        db.add(db_log)
        await db.commit()
        await db.refresh(db_log)
        return db_log

    async def get_by_user(self, db: AsyncSession, user_id: str):
        result = await db.execute(select(PromptLog).filter(PromptLog.user_id == user_id).order_by(PromptLog.created_at.desc()))
        return result.scalars().all()

prompt_repository = PromptRepository()
