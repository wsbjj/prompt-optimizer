from fastapi import APIRouter, Request, Response
import logging
import lark_oapi
from app.core.feishu import event_dispatcher

# 获取 logger 实例 (使用全局配置)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feishu", tags=["飞书接口"])

async def process_feishu_event(request: Request) -> Response:
    """
    统一的飞书事件处理入口
    
    将 FastAPI 的请求对象转换为 lark RawRequest，交由 
    EventDispatcherHandler 处理（负责验签、解密、事件分发）。
    
    Args:
        request: FastAPI 请求对象
        
    Returns:
        Response: HTTP 响应
    """
    try:
        # 1. 读取请求体
        body = await request.body()
        
        # 2. 构建 headers
        # lark SDK 需要从 headers 中读取签名相关的字段 (X-Lark-*)
        # FastAPI 的 request.headers 是 case-insensitive 的，但转成 dict 会变成小写
        # 这里手动构建一个包含正确 key 的字典
        raw_headers = dict(request.headers)
        headers = {}
        for key, value in raw_headers.items():
            headers[key] = value
            if key.startswith('x-lark'):
                # 将 x-lark-signature 转换为 X-Lark-Signature
                title_key = '-'.join(word.capitalize() for word in key.split('-'))
                headers[title_key] = value
        
        uri = request.url.path
        logger.debug(f"收到飞书事件回调 | uri: {uri} | body_size: {len(body)} bytes")
        
        # 3. 检查请求体
        if not body:
            logger.warning("收到空请求体")
            return Response(
                content=b'{"code": 4000, "message": "Empty request body"}',
                status_code=400,
                media_type="application/json; charset=utf-8"
            )

        # 4. 构造 RawRequest
        req = lark_oapi.RawRequest()
        req.uri = uri
        req.headers = headers
        req.body = body

        # 5. 调用事件分发器
        # event_dispatcher.do 会处理验签、解密、并调用注册的 handler
        resp = event_dispatcher.do(req)

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type="application/json; charset=utf-8"
        )

    except Exception as e:
        logger.error(f"处理飞书回调异常 | error: {str(e)}", exc_info=True)
        return Response(
            content=b'{"code": 5000, "message": "Internal server error"}',
            status_code=500,
            media_type="application/json; charset=utf-8"
        )

@router.post(
    "/callback",
    summary="飞书事件回调",
    description="接收飞书的事件回调（加密格式），包括URL验证和消息事件等"
)
async def feishu_callback(request: Request) -> Response:
    """
    飞书事件回调接口
    
    接收并处理飞书发送的加密事件回调。
    使用 EventDispatcherHandler 自动处理加密/解密和事件分发。
    
    - URL验证请求：自动返回 challenge 验证响应
    - 消息事件：通过事件分发器转发处理
    
    Args:
        request: FastAPI 请求对象
        
    Returns:
        Response: HTTP 响应（二进制）
    """
    return await process_feishu_event(request)

@router.post(
    "/event",
    summary="飞书事件Webhook",
    description="兼容开放平台示例的 /event 路径，处理 webhook 回调"
)
async def feishu_event(request: Request) -> Response:
    """
    飞书事件 Webhook 接口 (/event)
    
    功能与 /callback 相同，提供额外的路径支持。
    
    Args:
        request: FastAPI 请求对象
        
    Returns:
        Response: HTTP 响应
    """
    return await _process_feishu_event(request)
