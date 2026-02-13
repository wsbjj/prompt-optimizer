import json
import logging
import io
import lark_oapi
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody, GetMessageResourceRequest
from lark_oapi.api.report.v1 import QueryTaskRequest, QueryTaskRequestBody
from lark_oapi.api.contact.v3 import BatchUserRequest
from lark_oapi.api.bitable.v1 import CreateAppTableRecordRequest, AppTableRecord, ListAppTableRecordRequest, UpdateAppTableRecordRequest, DeleteAppTableRecordRequest
from app.core.feishu import client

logger = logging.getLogger(__name__)

class FeishuService:
    @staticmethod
    async def get_image_content(message_id: str, image_key: str) -> bytes:
        """获取飞书消息中的图片内容"""
        try:
            request = GetMessageResourceRequest.builder() \
                .message_id(message_id) \
                .file_key(image_key) \
                .type("image") \
                .build()
            response = await client.im.v1.message_resource.aget(request)
            if not response.success():
                logger.error(f"Failed to get image content: {response.msg} - {response.error}")
                return None
            if hasattr(response, 'file') and response.file:
                return response.file.read()
            return response.data
        except Exception as e:
            logger.error(f"Error getting image content: {e}", exc_info=True)
            return None

    @staticmethod
    async def get_report_tasks(start_time: int, end_time: int):
        """查询汇报任务"""
        try:
            request_body = QueryTaskRequestBody.builder() \
                .commit_start_time(start_time) \
                .commit_end_time(end_time) \
                .page_size(20) \
                .page_token("") \
                .build()
            request = QueryTaskRequest.builder() \
                .request_body(request_body) \
                .build()
            response = await client.report.v1.task.aquery(request)
            if not response.success():
                logger.error(f"Failed to query report tasks: {response.msg} - {response.error}")
                return None
            return response.data.items
        except Exception as e:
            logger.error(f"Error querying report tasks: {e}", exc_info=True)
            return None

    @staticmethod
    async def batch_get_users(user_ids: list[str]):
        """批量获取用户信息"""
        try:
            request = BatchUserRequest.builder() \
                .user_ids(user_ids) \
                .build()
            response = await client.contact.v3.user.abatch(request)
            if not response.success():
                logger.error(f"Failed to batch get users: {response.msg} - {response.error}")
                return None
            return response.data.items
        except Exception as e:
            logger.error(f"Error batch getting users: {e}", exc_info=True)
            return None

    @staticmethod
    async def create_bitable_record(app_token: str, table_id: str, fields: dict):
        """创建多维表格记录"""
        try:
            request = CreateAppTableRecordRequest.builder() \
                .app_token(app_token) \
                .table_id(table_id) \
                .request_body(AppTableRecord.builder().fields(fields).build()) \
                .build()
            response = await client.bitable.v1.app_table_record.acreate(request)
            if not response.success():
                code = getattr(response, 'code', 'unknown')
                msg = getattr(response, 'msg', 'unknown')
                error = getattr(response, 'error', 'unknown')
                logger.error(f"Failed to create bitable record: code={code}, msg={msg}, error={error}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error creating bitable record: {e}", exc_info=True)
            return False

    @staticmethod
    async def update_bitable_record(app_token: str, table_id: str, record_id: str, fields: dict):
        """更新多维表格记录"""
        try:
            request = UpdateAppTableRecordRequest.builder() \
                .app_token(app_token) \
                .table_id(table_id) \
                .record_id(record_id) \
                .request_body(AppTableRecord.builder().fields(fields).build()) \
                .build()
            response = await client.bitable.v1.app_table_record.aupdate(request)
            if not response.success():
                code = getattr(response, 'code', 'unknown')
                msg = getattr(response, 'msg', 'unknown')
                error = getattr(response, 'error', 'unknown')
                logger.error(f"Failed to update bitable record {record_id}: code={code}, msg={msg}, error={error}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error updating bitable record {record_id}: {e}", exc_info=True)
            return False

    @staticmethod
    async def delete_bitable_record(app_token: str, table_id: str, record_id: str):
        """删除多维表格记录"""
        try:
            request = DeleteAppTableRecordRequest.builder() \
                .app_token(app_token) \
                .table_id(table_id) \
                .record_id(record_id) \
                .build()
            response = await client.bitable.v1.app_table_record.adelete(request)
            if not response.success():
                code = getattr(response, 'code', 'unknown')
                msg = getattr(response, 'msg', 'unknown')
                error = getattr(response, 'error', 'unknown')
                logger.error(f"Failed to delete bitable record {record_id}: code={code}, msg={msg}, error={error}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error deleting bitable record {record_id}: {e}", exc_info=True)
            return False

    @staticmethod
    async def search_bitable_records(app_token: str, table_id: str, filter_str: str = None, page_token: str = None):
        """搜索多维表格记录"""
        try:
            builder = ListAppTableRecordRequest.builder().app_token(app_token).table_id(table_id).page_size(100)
            if filter_str:
                builder.filter(filter_str)
            if page_token:
                builder.page_token(page_token)
            request = builder.build()
            response = await client.bitable.v1.app_table_record.alist(request)
            if not response.success():
                logger.error(f"Failed to search bitable records: {response.msg} - {response.error}")
                return None
            return response.data.items
        except Exception as e:
            logger.error(f"Error searching bitable records: {e}", exc_info=True)
            return None

    @staticmethod
    async def send_card(receive_id: str, card_content: dict, receive_id_type: str = "open_id"):
        """发送飞书卡片消息"""
        try:
            request_body = CreateMessageRequestBody.builder() \
                .receive_id(receive_id) \
                .msg_type("interactive") \
                .content(json.dumps(card_content)) \
                .build()
            request = CreateMessageRequest.builder() \
                .receive_id_type(receive_id_type) \
                .request_body(request_body) \
                .build()
            response = await client.im.v1.message.acreate(request)
            if not response.success():
                logger.error(f"Failed to send card to {receive_id}: {response.msg} - {response.error}")
                return False
            logger.info(f"Successfully sent card to {receive_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending card to {receive_id}: {e}", exc_info=True)
            return False

    @staticmethod
    async def update_card(message_id: str, card_content: dict):
        """更新飞书卡片消息 (用于流式输出效果)"""
        try:
            response = await client.im.v1.message.apatch(
                lark_oapi.api.im.v1.PatchMessageRequest.builder()
                .message_id(message_id)
                .request_body(lark_oapi.api.im.v1.PatchMessageRequestBody.builder()
                    .content(json.dumps(card_content))
                    .build())
                .build()
            )
            if not response.success():
                logger.error(f"Failed to update card {message_id}: {response.msg} - {response.error}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error updating card {message_id}: {e}", exc_info=True)
            return False

    @staticmethod
    async def send_basic_mode_card(receive_id: str, receive_id_type: str = "open_id"):
        """发送基础模式切换成功卡片"""
        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"content": "✨ 已切换至基础模式", "tag": "plain_text"}
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"content": "您现在处于**基础模式**。\n请直接发送您的提示词草稿，我将为您优化。", "tag": "lark_md"}
                },
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": "💡 提示：您可以随时点击菜单切换其他模式"}]
                }
            ]
        }
        return await FeishuService.send_card(receive_id, card_content, receive_id_type)

    @staticmethod
    async def send_image_mode_card(receive_id: str, receive_id_type: str = "open_id"):
        """发送图片模式切换成功卡片"""
        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "wathet",
                "title": {"content": "🖼️ 已切换至图片模式", "tag": "plain_text"}
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"content": "您现在处于**图片模式**。\n请发送图片或详细的画面描述。", "tag": "lark_md"}
                },
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": "💡 提示：您可以随时点击菜单切换其他模式"}]
                }
            ]
        }
        return await FeishuService.send_card(receive_id, card_content, receive_id_type)

    @staticmethod
    async def send_search_mode_card(receive_id: str, receive_id_type: str = "open_id"):
        """发送关键词检索模式切换成功卡片"""
        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "orange",
                "title": {"content": "🔍 已切换至关键词检索模式", "tag": "plain_text"}
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"content": "您现在处于**关键词检索模式**。\n🚧 **该功能暂未实现，敬请期待！**", "tag": "lark_md"}
                },
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": "💡 提示：您可以随时点击菜单切换其他模式"}]
                }
            ]
        }
        return await FeishuService.send_card(receive_id, card_content, receive_id_type)

    @staticmethod
    async def send_report_mode_card(receive_id: str, receive_id_type: str = "open_id"):
        """发送日报周报总结模式切换成功卡片"""
        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "green",
                "title": {"content": "📊 已切换至日报周报模式", "tag": "plain_text"}
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "content": "您现在处于**日报周报总结模式**。\n\n您可以：\n1. **发送工作内容**（如\"今天完成了...明天计划...\"），我将为您生成专业日报。\n2. **查询历史汇报**（如\"查询昨天的日报\"），我将为您查找团队记录。\n3. **生成总结报告**，支持以下关键词：\n   - 📅 **日总结**：\"日总结\"、\"今日总结\"、\"昨天总结\"、\"02-09总结\"\n   - 📊 **周总结**：\"周总结\"、\"本周总结\"、\"上周总结\"、\"一周总结\"\n   - 📈 **月总结**：\"月总结\"、\"本月总结\"、\"上月总结\"、\"1月总结\"\n\n💡 提示：也支持复杂表达，如\"帮我看看这周的工作情况\"",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": "💡 提示：输入内容越详细，生成的日报越专业"}]
                }
            ]
        }
        return await FeishuService.send_card(receive_id, card_content, receive_id_type)

    @staticmethod
    async def send_optimization_result_card(receive_id: str, original_prompt: str, optimized_result: str, optimize_type: str):
        """发送优化结果卡片(非流式)"""
        display_original = original_prompt[:100] + "..." if len(original_prompt) > 100 else original_prompt
        display_content = optimized_result.strip().replace("```markdown", "").replace("```", "").strip()
        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "green",
                "title": {"content": "✅ 提示词优化完成", "tag": "plain_text"}
            },
            "elements": [
                {"tag": "div", "text": {"content": f"**原始提示词**\n{display_original}", "tag": "lark_md"}},
                {"tag": "div", "text": {"content": f"**优化结果**\n{display_content}", "tag": "lark_md"}},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"模式: {optimize_type}"}]}
            ]
        }
        return await FeishuService.send_card(receive_id, card_content)

    @staticmethod
    async def send_optimization_stream_start_card(receive_id: str, original_prompt: str, optimize_type: str = "基础模式"):
        """发送流式生成开始卡片"""
        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"content": "🚀 正在生成优化结果...", "tag": "plain_text"}
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"content": f"**原始提示词**：\n{original_prompt}\n\n**优化结果**：\n(思考中...)", "tag": "lark_md"}
                }
            ]
        }
        try:
            request_body = CreateMessageRequestBody.builder() \
                .receive_id(receive_id) \
                .msg_type("interactive") \
                .content(json.dumps(card_content)) \
                .build()
            request = CreateMessageRequest.builder().receive_id_type("open_id").request_body(request_body).build()
            response = await client.im.v1.message.acreate(request)
            return response.data.message_id if response.success() else None
        except Exception as e:
            logger.error(f"Error sending stream start card: {e}")
            return None

    @staticmethod
    async def update_optimization_stream_card(message_id: str, original_prompt: str, current_content: str, is_finished: bool = False):
        """更新流式卡片内容"""
        title = "✅ 提示词优化完成" if is_finished else "🚀 正在生成优化结果..."
        template = "green" if is_finished else "blue"
        display_content = current_content.strip().replace("```markdown", "").replace("```", "").strip()
        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {"template": template, "title": {"content": title, "tag": "plain_text"}},
            "elements": [
                {
                    "tag": "div",
                    "text": {"content": f"**原始提示词**：\n{original_prompt}\n\n**优化结果**：\n{display_content}", "tag": "lark_md"}
                }
            ]
        }
        return await FeishuService.update_card(message_id, card_content)

    @staticmethod
    async def send_clarification_questions(receive_id: str, questions: list, reason: str):
        """发送澄清问题卡片"""
        q_text = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "orange",
                "title": {"content": "🤔 需要您补充一点细节", "tag": "plain_text"}
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"content": f"为了提供更精准的提示词，我需要了解更多信息：\n\n**{reason}**\n\n请直接回复以下问题的答案：\n{q_text}", "tag": "lark_md"}
                },
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": "💡 直接回复答案即可，我会结合您的回答进行最终优化"}]
                }
            ]
        }
        return await FeishuService.send_card(receive_id, card_content)

    @staticmethod
    async def send_text(receive_id: str, text: str, receive_id_type: str = "open_id"):
        """发送飞书文本消息"""
        try:
            request_body = CreateMessageRequestBody.builder() \
                .receive_id(receive_id) \
                .msg_type("text") \
                .content(json.dumps({"text": text})) \
                .build()
            request = CreateMessageRequest.builder().receive_id_type(receive_id_type).request_body(request_body).build()
            response = await client.im.v1.message.acreate(request)
            return response.success()
        except Exception as e:
            logger.error(f"Error sending text to {receive_id}: {e}", exc_info=True)
            return False

    @staticmethod
    async def send_image_analysis_stream_start_card(receive_id: str):
        """发送图片分析流式开始卡片"""
        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {"template": "blue", "title": {"content": "🖼️ 正在分析画面...", "tag": "plain_text"}},
            "elements": [{"tag": "div", "text": {"content": "正在观察画面细节，生成画面摘要..", "tag": "lark_md"}}]
        }
        try:
            request_body = CreateMessageRequestBody.builder() \
                .receive_id(receive_id) \
                .msg_type("interactive") \
                .content(json.dumps(card_content)) \
                .build()
            request = CreateMessageRequest.builder().receive_id_type("open_id").request_body(request_body).build()
            response = await client.im.v1.message.acreate(request)
            return response.data.message_id if response.success() else None
        except Exception as e:
            logger.error(f"Error sending image analysis card: {e}")
            return None

    @staticmethod
    async def update_image_analysis_card(message_id: str, content: str, is_finished: bool = False):
        """更新图片分析卡片"""
        title = "✅ 图片分析完成" if is_finished else "🖼️ 正在分析画面..."
        template = "green" if is_finished else "blue"
        display_content = content.strip()
        if is_finished:
            display_content += "\n\n**请发送您的提示词指令，我将结合画面信息为您优化！**"
        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {"template": template, "title": {"content": title, "tag": "plain_text"}},
            "elements": [{"tag": "div", "text": {"content": f"**【画面摘要】：**\n{display_content}", "tag": "lark_md"}}]
        }
        return await FeishuService.update_card(message_id, card_content)

    @staticmethod
    async def send_weekly_summary_stream_start_card(receive_id: str, date_range_desc: str):
        """发送周总结流式开始卡片"""
        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {"template": "purple", "title": {"content": "📊 正在生成周度递归进步总结...", "tag": "plain_text"}},
            "elements": [
                {
                    "tag": "div",
                    "text": {"content": f"**📅 分析周期**: {date_range_desc}\n\n正在拉取日报数据并进行递归分析，请稍候..", "tag": "lark_md"}
                }
            ]
        }
        try:
            request_body = CreateMessageRequestBody.builder() \
                .receive_id(receive_id) \
                .msg_type("interactive") \
                .content(json.dumps(card_content)) \
                .build()
            request = CreateMessageRequest.builder().receive_id_type("open_id").request_body(request_body).build()
            response = await client.im.v1.message.acreate(request)
            return response.data.message_id if response.success() else None
        except Exception as e:
            logger.error(f"Error sending weekly summary start card: {e}")
            return None

    @staticmethod
    async def update_weekly_summary_card(message_id: str, content: str, date_range_desc: str, is_finished: bool = False):
        """更新周总结流式卡片内容"""
        title = "✅ 周度递归进步总结完成" if is_finished else "📊 正在生成周度递归进步总结..."
        template = "green" if is_finished else "purple"
        display_content = content.strip().replace("```markdown", "").replace("```", "").strip()
        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {"template": template, "title": {"content": title, "tag": "plain_text"}},
            "elements": [
                {
                    "tag": "div",
                    "text": {"content": f"**📅 分析周期**: {date_range_desc}\n\n{display_content}", "tag": "lark_md"}
                }
            ]
        }
        return await FeishuService.update_card(message_id, card_content)

feishu_service = FeishuService()