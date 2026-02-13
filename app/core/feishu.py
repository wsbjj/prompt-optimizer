import lark_oapi
from lark_oapi import EventDispatcherHandler
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from app.core.config import settings

# 初始化 Lark 客户端
client = lark_oapi.Client.builder() \
    .app_id(settings.FEISHU_APP_ID) \
    .app_secret(settings.FEISHU_APP_SECRET) \
    .log_level(lark_oapi.LogLevel.INFO) \
    .build()

# 延迟导入 handler 以避免循环依赖
from app.handlers.feishu_handler import message_handler, menu_handler, p2p_chat_entered_handler

# 初始化事件分发器并注册处理器
event_dispatcher = EventDispatcherHandler.builder(
    settings.FEISHU_ENCRYPT_KEY,
    settings.FEISHU_VERIFICATION_TOKEN,
    lark_oapi.LogLevel.INFO
).register_p2_im_message_receive_v1(message_handler) \
 .register_p2_application_bot_menu_v6(menu_handler) \
 .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(p2p_chat_entered_handler) \
 .build()
