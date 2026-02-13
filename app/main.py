from fastapi import FastAPI, Request, Response
from app.controllers import feishu_controller
from app.core.database import engine, Base
from app.core.logger import setup_logging
from app.services.report_analysis_service import ReportAnalysisService
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import uvicorn
import logging
import time
from datetime import datetime, timedelta

# 初始化日志配置
setup_logging()
logger = logging.getLogger(__name__)

async def daily_sync_and_summary():
    """每天21:00执行：同步日报 + 生成日总结 + 周日生成周总结 + 月末生成月总结"""
    import calendar
    service = ReportAnalysisService()
    
    # Step 1: 同步并分析当天的日报
    logger.info("🔄 开始执行每日日报同步与分析...")
    await service.sync_and_analyze(hours=24)
    
    now = datetime.now()
    
    # Step 2: 每天生成日总结
    logger.info("📅 开始生成日总结...")
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    daily_count = await service.daily_summary_and_save(int(day_start.timestamp()), int(day_end.timestamp()))
    logger.info(f"✅ 日总结完成，处理了 {daily_count} 位用户")
    
    # Step 3: 如果是周日，额外生成周总结
    if now.weekday() == 6:  # Sunday
        logger.info("📊 今天是周日，生成周总结...")
        days_since_monday = now.weekday()
        this_monday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
        weekly_count = await service.weekly_summary_and_save(int(this_monday.timestamp()), int(now.timestamp()))
        logger.info(f"✅ 周总结完成，处理了 {weekly_count} 位用户")
    
    # Step 4: 如果是月末最后一天，额外生成月总结
    _, last_day = calendar.monthrange(now.year, now.month)
    if now.day == last_day:
        logger.info("📈 今天是月末，生成月总结...")
        month_start = datetime(now.year, now.month, 1, 0, 0, 0)
        month_end = datetime(now.year, now.month, last_day, 23, 59, 59)
        monthly_count = await service.monthly_summary_and_save(int(month_start.timestamp()), int(month_end.timestamp()))
        logger.info(f"✅ 月总结完成，处理了 {monthly_count} 位用户")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up application...")
    
    # 初始化数据库表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 初始化并启动调度器
    scheduler = AsyncIOScheduler()
    
    # 每天 21:00 执行：同步日报 + 生成周递归总结
    scheduler.add_job(
        daily_sync_and_summary, 
        'cron', 
        hour=21, 
        minute=0, 
        second=0
    )
    
    scheduler.start()
    logger.info("Scheduler started. Daily sync & summary job scheduled for 21:00.")
    
    yield
    
    scheduler.shutdown()
    logger.info("Shutting down application...")

app = FastAPI(title="Prompt Optimizer Bot", version="1.0.0", lifespan=lifespan)

app.include_router(feishu_controller.router)

@app.get("/")
async def root():
    return {"message": "Prompt Optimizer Bot is running"}

@app.post("/")
async def root_post(request: Request) -> Response:
    """
    处理飞书回调 (兼容模式)
    如果飞书应用配置的回调地址是根路径，则通过此接口处理
    """
    return await feishu_controller.process_feishu_event(request)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
