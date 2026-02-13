import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from app.core.config import settings

def setup_logging():
    """
    配置全局日志记录器
    输出：
    1. 控制台 (Console)
    2. 文件 (logs/app.log)
    """
    # 确保日志目录存在
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file_path = os.path.join(log_dir, "app.log")

    # 获取配置的日志级别
    log_level = settings.LOG_LEVEL.upper()
    
    # 统一的日志格式
    # 格式：[时间] [级别] [模块:行号] - 消息
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(module)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # 2. 文件处理器 (自动轮转：10MB切割，保留5个备份)
    file_handler = RotatingFileHandler(
        log_file_path, 
        maxBytes=10*1024*1024, # 10MB
        backupCount=5, 
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除旧的处理器（防止重复日志）
    if root_logger.handlers:
        root_logger.handlers = []

    # 添加新的处理器
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # 针对 uvicorn 和 fastapi 的日志进行调整
    logging.getLogger("uvicorn.access").handlers = [console_handler, file_handler]
    logging.getLogger("uvicorn.error").handlers = [console_handler, file_handler]
    
    # 屏蔽 httpcore 和 httpx 的 DEBUG 日志 (它们非常啰嗦)
    # logging.getLogger("httpcore").setLevel(logging.WARNING)
    # logging.getLogger("httpx").setLevel(logging.WARNING)
    # logging.getLogger("openai").setLevel(logging.WARNING)
    
    # 记录一条启动日志
    logging.info(f"Logging initialized at level: {log_level}")
    logging.info(f"Log file path: {os.path.abspath(log_file_path)}")
