import json
import logging
import asyncio
import datetime
import lark_oapi
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1, P2ImChatAccessEventBotP2pChatEnteredV1
from lark_oapi.api.application.v6.model import P2ApplicationBotMenuV6
from app.services.prompt_service import PromptService, OptimizeType
from app.core.database import SessionLocal
from app.repositories.prompt_repository import PromptRepository
from app.core.redis import state_manager
from app.core.prompts import PromptTemplate, PROMPTS
from app.core.llm import LLMClient

logger = logging.getLogger(__name__)
prompt_service = PromptService()
prompt_repository = PromptRepository()

async def parse_report_date_intent(user_input: str) -> tuple[int, int, str]:
    """
    解析用户输入的日期意图
    Returns: (start_timestamp, end_timestamp, date_description)
    """
    try:
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        prompt = PROMPTS[PromptTemplate.REPORT_INTENT_RECOGNITION].format(
            current_date=current_date,
            user_input=user_input
        )
        
        logger.info(f"Date intent prompt: {prompt}")
        
        # Call LLM
        llm_client = LLMClient()
        response_text = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, # Low temperature for deterministic output
            max_tokens=100
        )
        
        logger.info(f"Date intent raw response: {response_text}")

        # Parse JSON
        # Clean up markdown code blocks if present
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
            
        date_data = json.loads(cleaned_text.strip())
        start_str = date_data.get("start_date")
        end_str = date_data.get("end_date")
        
        # Convert to timestamps
        # Start time: 00:00:00 of start_date
        start_dt = datetime.datetime.strptime(start_str, "%Y-%m-%d")
        start_ts = int(start_dt.timestamp())
        
        # End time: 23:59:59 of end_date
        end_dt = datetime.datetime.strptime(end_str, "%Y-%m-%d") + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)
        end_ts = int(end_dt.timestamp())
        
        date_desc = f"{start_str}" if start_str == end_str else f"{start_str} 至 {end_str}"
        return start_ts, end_ts, date_desc
        
    except Exception as e:
        logger.error(f"Error parsing date intent: {e}")
        # Fallback to today
        today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_ts = int(today.timestamp())
        end_ts = int((today + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)).timestamp())
        return start_ts, end_ts, today.strftime("%Y-%m-%d")

async def _message_handler_impl(event: P2ImMessageReceiveV1):
    """
    处理飞书接收消息事件 (Async Implementation)
    """
    from app.services.feishu_service import feishu_service
    logger.info(f"Received message event: {event.event.message.message_id}")
    
    # 1. 解析消息内容
    message_content_json = event.event.message.content
    msg_type = event.event.message.message_type
    sender_id = event.event.sender.sender_id.open_id
    
    # 获取用户当前模式
    current_mode = await state_manager.get_user_mode(sender_id)

    # 如果用户没有选择模式，提示选择
    if not current_mode:
        reply_text = "🔴 会话已过期或未开始。\n请点击底部菜单栏选择一个功能模式 (如：基础模式、关键词检索等) 以开始会话。"
        await feishu_service.send_text(sender_id, reply_text)
        return

    # --- 图片消息处理 ---
    if msg_type == "image":
        if current_mode == MENU_IMAGE_MODE:
            try:
                content_dict = json.loads(message_content_json)
                image_key = content_dict.get("image_key")
                message_id = event.event.message.message_id
                
                # 1. 发送开始分析卡片
                analysis_msg_id = await feishu_service.send_image_analysis_stream_start_card(sender_id)
                
                # 2. 下载图片
                image_data = await feishu_service.get_image_content(message_id, image_key)
                if not image_data:
                    await feishu_service.send_text(sender_id, "❌ 图片下载失败，请重试。")
                    return

                # 3. 视觉模型流式分析
                image_desc = ""
                last_update_len = 0
                
                async for chunk in prompt_service.analyze_image_stream(image_data):
                    image_desc += chunk
                    # 每生成20个字符更新一次卡片，减少API调用频率
                    if len(image_desc) - last_update_len >= 20:
                        await feishu_service.update_image_analysis_card(analysis_msg_id, image_desc, is_finished=False)
                        last_update_len = len(image_desc)
                
                # 4. 完成更新
                await feishu_service.update_image_analysis_card(analysis_msg_id, image_desc, is_finished=True)
                
                # 5. 保存图片描述到 Redis (关联用户)
                # 使用 user_id:image_desc 作为 key，TTL 10分钟
                await state_manager.set_value(f"{sender_id}:image_desc", image_desc, ttl=600)
                
                return
            except Exception as e:
                logger.error(f"Error processing image: {e}", exc_info=True)
                await feishu_service.send_text(sender_id, "❌ 图片处理出错，请重试。")
                return
        else:
            await feishu_service.send_text(sender_id, "⚠️ 当前不在图片模式，无法处理图片。请先切换到【图片模式】。")
            return

    # --- 文本消息处理 ---
    if msg_type != "text":
        logger.info(f"Ignored message type: {msg_type}")
        return

    try:
        content_dict = json.loads(message_content_json)
        text = content_dict.get("text", "")
        input_content = text.strip()  # Initialize input_content here
    except Exception as e:
        logger.error(f"Failed to parse message content: {e}")
        return

    # 路由分发：关键词检索模式
    if current_mode == MENU_SEARCH_MODE:
        # TODO: 对接关键词检索服务
        reply_text = f"🔍 正在为您检索关键词：【{text.strip()}】\n\n(功能开发中...)"
        await feishu_service.send_text(sender_id, reply_text)
        return
        
    # 路由分发：日报周报模式
    elif current_mode == MENU_REPORT_MODE:
        input_text = text.strip()
        
        # --- 手动触发同步逻辑 ---
        # 如果用户输入包含特定关键词，立即执行同步任务
        sync_keywords = ["同步日报", "立即运行", "手动同步", "运行同步", "sync reports"]
        if any(k in input_text for k in sync_keywords):
            await feishu_service.send_text(sender_id, "🚀 收到指令，正在立即运行日报同步与分析任务...")
            try:
                # Local import to avoid circular dependencies
                from app.services.report_analysis_service import ReportAnalysisService
                service = ReportAnalysisService()
                # 默认同步 24 小时
                await service.sync_and_analyze(hours=24)
                await feishu_service.send_text(sender_id, "✅ 日报同步与分析任务执行完成！")
            except Exception as e:
                logger.error(f"Manual sync failed: {e}", exc_info=True)
                await feishu_service.send_text(sender_id, f"❌ 任务执行失败: {str(e)}")
            return
        # -----------------------

        # --- 总结意图识别（关键词优先 + LLM兜底） ---
        intent_type = "none"
        date_info = ""
        
        # 关键词匹配（快速且可靠）
        import re
        
        # 日总结关键词：包含"日总结"、日期格式"XX-XX总结"、"今天/昨天/今日总结"
        if re.search(r'(日总结|今日总结|今天总结|昨天总结|前天总结|\d{1,2}-\d{1,2}总结)', input_text):
            intent_type = "daily"
            # 提取日期信息
            date_match = re.search(r'(\d{1,2}-\d{1,2}|昨天|今天|今日|前天)', input_text)
            date_info = date_match.group(1) if date_match else "今天"
            
        # 周总结关键词：包含"周总结"、"本周/上周/一周总结"、"week"
        elif re.search(r'(周总结|本周总结|上周总结|一周总结|周报总结|week\s*summary)', input_text, re.IGNORECASE):
            intent_type = "weekly"
            # 提取周期信息
            if "上周" in input_text or "last week" in input_text.lower():
                date_info = "上周"
            else:
                date_info = "本周"
                
        # 月总结关键词：包含"月总结"、"X月总结"、"本月/上月总结"
        elif re.search(r'(月总结|本月总结|上月总结|\d+月总结|month\s*summary)', input_text, re.IGNORECASE):
            intent_type = "monthly"
            # 提取月份信息
            month_match = re.search(r'(\d+月|上月|本月)', input_text)
            date_info = month_match.group(1) if month_match else "本月"
        
        # 关键词未匹配，尝试LLM识别（处理复杂表达）
        else:
            try:
                from app.services.report_analysis_service import ReportAnalysisService
                summary_service = ReportAnalysisService()
                intent = await summary_service.recognize_summary_intent(input_text)
                intent_type = intent.get("type", "none")
                date_info = intent.get("date_info", "")
                logger.info(f"LLM intent recognition: type={intent_type}, date_info={date_info}")
            except Exception as e:
                logger.warning(f"LLM intent recognition failed, falling back to none: {e}")
                intent_type = "none"
                date_info = ""

        if intent_type in ("daily", "weekly", "monthly"):
            try:
                from app.services.report_analysis_service import ReportAnalysisService
                service = ReportAnalysisService()
                
                # 解析日期范围
                start_ts, end_ts, date_range_desc = service.parse_date_range(intent_type, date_info)
                
                if not start_ts or not end_ts:
                    await feishu_service.send_text(sender_id, "❌ 无法解析目标日期，请重试。")
                    return
                
                # 总结类型标签
                type_labels = {"daily": "日总结", "weekly": "周总结", "monthly": "月总结"}
                type_label = type_labels[intent_type]
                
                # 发送流式开始卡片
                message_id = await feishu_service.send_weekly_summary_stream_start_card(
                    sender_id, f"{date_range_desc} ({type_label})"
                )
                
                if not message_id:
                    await feishu_service.send_text(sender_id, "❌ 发送卡片失败，请重试。")
                    return

                # 根据类型选择对应的流式方法
                full_content = ""
                last_update_len = 0
                
                if intent_type == "daily":
                    stream = service.daily_summary_stream(start_ts, end_ts, save_to_bitable=True)
                elif intent_type == "weekly":
                    stream = service.weekly_recursive_summary_stream(start_ts, end_ts, save_to_bitable=True)
                else:  # monthly
                    stream = service.monthly_summary_stream(start_ts, end_ts, save_to_bitable=True)
                
                async for chunk in stream:
                    full_content += chunk
                    if len(full_content) - last_update_len >= 30:
                        await feishu_service.update_weekly_summary_card(
                            message_id, full_content, f"{date_range_desc} ({type_label})", is_finished=False
                        )
                        last_update_len = len(full_content)
                
                # 最终更新：仅展示摘要
                summary, score = service._extract_summary_and_score(full_content)
                summary_display = f"**🏆 {type_label}评分: {score}/100**\n\n{summary}\n\n> 💡 完整分析报告已写入云文档"
                await feishu_service.update_weekly_summary_card(
                    message_id, summary_display, f"{date_range_desc} ({type_label})", is_finished=True
                )
                
            except Exception as e:
                logger.error(f"Summary generation failed: {e}", exc_info=True)
                await feishu_service.send_text(sender_id, f"❌ 总结生成失败: {str(e)}")
            return
        # -----------------------


        # 1. 尝试识别日期意图
        # 如果用户明确包含 "查询"、"查看"、"看看" 等关键词，则认为是查询模式
        query_keywords = ["查询", "查看", "看看", "找一下", "搜索"]
        is_query_intent = any(k in input_text for k in query_keywords)
        
        # 即使不是明确的查询词，如果是非常短的日期描述（如"昨天"、"今天的"），也可能是查询
        # 但如果包含"完成"、"计划"、"做了"等词，更可能是汇报内容
        # 关键词列表优化：避免 "进度" 这种模棱两可的词导致误判
        report_keywords = ["完成", "计划", "做了", "待办", "今日", "明日", "思考", "逻辑", "实现"]
        is_report_content = any(k in input_text for k in report_keywords)
        
        # 补充逻辑：如果包含查询词，但文本长度超过一定限制（例如 15 字），且包含数字序号（1. 2.），大概率是汇报内容（例如 "1. 查看了文档"）
        if is_query_intent and len(input_text) > 15 and any(char.isdigit() for char in input_text):
            is_query_intent = False
            
        if is_query_intent and not is_report_content:
             # --- 纯查询逻辑 ---
            start_time, end_time, target_date_str = await parse_report_date_intent(input_text)
            
            await feishu_service.send_text(sender_id, f"🔍 正在查询 {target_date_str} 的汇报记录，请稍候...")
            
            # Step 1: Query report tasks
            tasks = await feishu_service.get_report_tasks(start_time, end_time)
            
            if not tasks:
                await feishu_service.send_text(sender_id, f"⚠️ {target_date_str}暂无汇报记录。")
                return

            # Step 2: Extract user IDs
            user_ids = list(set([task.from_user_id for task in tasks if hasattr(task, 'from_user_id')]))
            
            if not user_ids:
                 await feishu_service.send_text(sender_id, f"⚠️ {target_date_str}暂无有效汇报提交。")
                 return

            # Step 3: Batch get users
            user_map = {}
            for task in tasks:
                if hasattr(task, 'from_user_id') and hasattr(task, 'from_user_name'):
                     user_map[task.from_user_id] = task.from_user_name

            missing_ids = [uid for uid in user_ids if uid not in user_map]
            if missing_ids:
                chunk_size = 50
                for i in range(0, len(missing_ids), chunk_size):
                    chunk = missing_ids[i:i + chunk_size]
                    users = await feishu_service.batch_get_users(chunk)
                    if users:
                        for user in users:
                            if hasattr(user, 'name') and user.name:
                                 user_map[user.open_id] = user.name
                            elif hasattr(user, 'en_name') and user.en_name:
                                 user_map[user.open_id] = user.en_name

            # Step 4: Assemble Data
            report_list = []
            for task in tasks:
                if not hasattr(task, 'from_user_id'):
                    continue
                
                user_name = user_map.get(task.from_user_id, task.from_user_name if hasattr(task, 'from_user_name') else "未知用户")
                submit_time = "未知时间"
                if hasattr(task, 'commit_time'):
                     try:
                         submit_time = datetime.datetime.fromtimestamp(int(task.commit_time)).strftime('%H:%M')
                     except:
                         pass
                
                report_list.append(f"✅ {user_name} ({submit_time})")

            # Send summary
            summary_text = "\n".join(report_list)
            msg = f"📊 **{target_date_str}汇报统计** (共 {len(report_list)} 条)：\n\n{summary_text}"
            await feishu_service.send_text(sender_id, msg)
            return
            
        else:
            # --- 汇报优化逻辑 ---
            # 即使不是查询，我们也尝试获取昨天的日报作为上下文（隐式查询）
            context_str = ""
            try:
                # 获取昨天的日期范围
                today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                yesterday = today - datetime.timedelta(days=1)
                start_ts = int(yesterday.timestamp())
                end_ts = int((yesterday + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)).timestamp())
                
                # 查询昨天的所有任务
                tasks = await feishu_service.get_report_tasks(start_ts, end_ts)
                
                # 筛选出当前用户的任务
                # 注意：Tasks API返回的是所有人的，我们需要匹配 sender_id (open_id)
                # Task 对象中 from_user_id 通常是 user_id (union_id or user_id?), 飞书 API 这里的 from_user_id 对应用户的 ID
                # 我们需要确认 sender_id (open_id) 是否能匹配。通常 API 返回的是 user_id。
                # 如果无法精确匹配，可能无法提供上下文。这里尝试做一个简单的匹配或跳过。
                # 由于无法确定 ID 映射，这里暂时只尝试获取（如果后续能打通 ID 更好）
                # 为了演示，我们假设如果找到了同名用户（如果有名字）或者 ID 匹配
                
                # 简化处理：如果找到了任何汇报，先不强行匹配具体内容，除非有确切 ID。
                # 但为了给 LLM 提供上下文，我们可以把“昨天团队的整体工作”作为背景，或者如果能找到自己的更好。
                # 暂时跳过复杂的 ID 匹配，只在 Prompt 中预留位置。
                pass 
            except Exception as e:
                logger.warning(f"Failed to fetch context reports: {e}")

            # 启动流式生成 - 汇报优化
            message_id = await feishu_service.send_optimization_stream_start_card(
                receive_id=sender_id,
                original_prompt=input_text,
                optimize_type="日报优化"
            )
            
            if not message_id:
                await feishu_service.send_text(sender_id, "❌ 发送卡片失败，请重试。")
                return

            try:
                full_content = ""
                # 使用 REPORT 模式
                async for chunk in prompt_service.optimize_stream(
                    prompt=input_text,
                    optimize_type=OptimizeType.REPORT
                ):
                    full_content += chunk
                    if len(full_content) % 10 == 0:
                        await feishu_service.update_optimization_stream_card(message_id, input_text, full_content, is_finished=False)
                
                await feishu_service.update_optimization_stream_card(message_id, input_text, full_content, is_finished=True)
                return

            except Exception as e:
                logger.error(f"Error optimizing report: {e}", exc_info=True)
                await feishu_service.send_text(sender_id, "❌ 优化过程出错，请重试。")
                return

    # 路由分发：图片模式 (文本指令)
    elif current_mode == MENU_IMAGE_MODE:
        # 检查是否有图片上下文
        image_desc = await state_manager.get_value(f"{sender_id}:image_desc")
        
        if not image_desc:
            # 尝试获取上一轮的待处理输入
            pending_input = await state_manager.get_value(f"{sender_id}:pending_text_input")
            
            # 分析当前输入意图
            intent = await prompt_service.analyze_image_mode_intent(input_content)
            
            target_input = input_content
            should_optimize = False
            
            if intent == "GEN_IMAGE":
                # 用户输入了画面描述，直接优化
                should_optimize = True
            elif intent == "FORCE_TEXT":
                # 用户强制要求直接优化
                if pending_input:
                    # 如果有暂存的描述，使用暂存描述
                    target_input = pending_input
                    should_optimize = True
                    # 清除暂存
                    await state_manager.delete_value(f"{sender_id}:pending_text_input")
                else:
                    # 如果没有暂存，且当前输入只是“直接优化”，无法优化
                    # 除非当前输入本身包含描述（但这通常会被判为 GEN_IMAGE）
                    # 这里假设 FORCE_TEXT 通常不包含描述，所以提示用户
                    await feishu_service.send_text(sender_id, "⚠️ 请提供具体的画面描述，然后我会为您生成提示词。")
                    return
            else:
                # 其他情况（闲聊或无关），暂存输入并提示
                # 只有当输入有一定长度时才暂存，避免存入“你好”之类
                if len(input_content) > 5:
                    await state_manager.set_value(f"{sender_id}:pending_text_input", input_content, ttl=600)
                
                await feishu_service.send_text(sender_id, "⚠️ 当前为图片模式，建议先发送参考图片。\n\n如果您希望直接根据文字生成‘欧美写实’风格提示词，请回复 **“直接优化”** (将使用刚才的文字) 或直接发送新的详细画面描述。")
                return

            if should_optimize:
                try:
                    # 启动流式生成
                    message_id = await feishu_service.send_optimization_stream_start_card(
                        receive_id=sender_id,
                        original_prompt=f"[图片模式-纯文字] {target_input}",
                        optimize_type="图片模式"
                    )

                    if not message_id:
                        await feishu_service.send_text(sender_id, "❌ 发送卡片失败，请重试。")
                        return

                    # 构造强化 Prompt
                    constructed_prompt = f"""【用户原始指令】：
{target_input}

【优化目标】：
请将上述文字描述转化为符合“欧美写实·产品场景化”生成逻辑 (Golden Prompt Formula) 的摄影级提示词。"""

                    full_content = ""
                    async for chunk in prompt_service.optimize_stream(
                        prompt=constructed_prompt,
                        optimize_type=OptimizeType.IMAGE
                    ):
                        full_content += chunk
                        if len(full_content) % 10 == 0:
                            await feishu_service.update_optimization_stream_card(message_id, f"[图片模式-纯文字] {target_input}", full_content, is_finished=False)
                    
                    await feishu_service.update_optimization_stream_card(message_id, f"[图片模式-纯文字] {target_input}", full_content, is_finished=True)
                    return

                except Exception as e:
                    logger.error(f"Error optimizing text-only image prompt: {e}", exc_info=True)
                    await feishu_service.send_text(sender_id, "❌ 优化过程出错，请重试。")
                    return
            
        input_content = text.strip()
        
        # 调用图片优化服务 (流式)
        try:
            # 启动流式生成
            message_id = await feishu_service.send_optimization_stream_start_card(
                receive_id=sender_id,
                original_prompt=f"[基于图片] {input_content}",
                optimize_type="图片模式"
            )

            if not message_id:
                await feishu_service.send_text(sender_id, "❌ 发送卡片失败，请重试。")
                return

            full_content = ""
            async for chunk in prompt_service.optimize_with_image_stream(
                user_instruction=input_content,
                image_description=image_desc
            ):
                full_content += chunk
                # 每积累一定长度更新一次卡片，避免过于频繁
                if len(full_content) % 10 == 0:
                    await feishu_service.update_optimization_stream_card(message_id, f"[基于图片] {input_content}", full_content, is_finished=False)
            
            # 最终更新
            await feishu_service.update_optimization_stream_card(message_id, f"[基于图片] {input_content}", full_content, is_finished=True)
            return

        except Exception as e:
            logger.error(f"Error optimizing image prompt: {e}", exc_info=True)
            await feishu_service.send_text(sender_id, "❌ 优化过程出错，请重试。")
            return
    
    # 默认流程：基础模式 (Prompt优化)
    # 2. 简单的意图识别
    optimize_type = OptimizeType.USER_BASIC
    input_content = text.strip()
    
    # 检查是否有待澄清的上下文
    # 使用 user_id:clarification_context 存储上一轮的原始问题
    last_prompt = await state_manager.get_value(f"{sender_id}:clarification_context")
    
    if last_prompt:
        # 这是一个对澄清问题的回答
        await feishu_service.send_text(sender_id, "✅ 收到您的补充信息，正在为您生成最终提示词...")
        
        # 清除上下文状态
        await state_manager.delete_value(f"{sender_id}:clarification_context")
        
        # 启动流式生成
        message_id = await feishu_service.send_optimization_stream_start_card(
            receive_id=sender_id, 
            original_prompt=last_prompt, 
            optimize_type="基础模式"
        )
        
        if not message_id:
            await feishu_service.send_text(sender_id, "❌ 发送卡片失败，请重试。")
            return

        try:
            full_content = ""
            # 使用优化后的提示词（带上下文）
            async for chunk in prompt_service.optimize_stream(
                prompt=last_prompt, 
                optimize_type=OptimizeType.USER_BASIC,
                context=input_content # 用户的回答作为上下文
            ):
                full_content += chunk
                # 每积累一定长度更新一次卡片，避免过于频繁
                if len(full_content) % 10 == 0: 
                    await feishu_service.update_optimization_stream_card(message_id, last_prompt, full_content, is_finished=False)
            
            # 最终更新
            await feishu_service.update_optimization_stream_card(message_id, last_prompt, full_content, is_finished=True)
            
        except Exception as e:
            logger.error(f"Error in stream optimization: {e}", exc_info=True)
            await feishu_service.send_text(sender_id, "❌ 优化过程出错，请重试。")
        
        return

    # 新的请求：先分析是否需要澄清
    if input_content.lower().startswith("sys:") or input_content.startswith("系统:"):
        optimize_type = OptimizeType.SYSTEM
        input_content = input_content.split(":", 1)[1].strip()
    
    # 分析澄清需求
    analysis = await prompt_service.analyze_need_for_clarification(input_content)
    
    if analysis.get("needs_clarification"):
        questions = analysis.get("questions", [])
        reason = analysis.get("reason", "")
        
        # 保存当前问题的上下文，以便下一轮使用
        await state_manager.set_value(f"{sender_id}:clarification_context", input_content, ttl=600)
        
        await feishu_service.send_clarification_questions(sender_id, questions, reason)
        return

    # 不需要澄清，直接流式生成
    message_id = await feishu_service.send_optimization_stream_start_card(
        receive_id=sender_id, 
        original_prompt=input_content, 
        optimize_type="基础模式"
    )
    
    if not message_id:
        await feishu_service.send_text(sender_id, "❌ 发送卡片失败，请重试。")
        return

    try:
        full_content = ""
        async for chunk in prompt_service.optimize_stream(input_content, optimize_type):
            full_content += chunk
            if len(full_content) % 10 == 0:
                await feishu_service.update_optimization_stream_card(message_id, input_content, full_content, is_finished=False)
        
        await feishu_service.update_optimization_stream_card(message_id, input_content, full_content, is_finished=True)
        
    except Exception as e:
        logger.error(f"Error in stream optimization: {e}", exc_info=True)
        await feishu_service.send_text(sender_id, "❌ 优化过程出错，请重试。")

def message_handler(event: P2ImMessageReceiveV1):
    """
    处理飞书接收消息事件 (Sync Wrapper)
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_message_handler_impl(event))
    except RuntimeError:
        logger.warning("No running loop found, creating new loop for message_handler")
        asyncio.run(_message_handler_impl(event))

# 菜单事件 Key 定义
MENU_BASIC_MODE = "MENU_BASIC_MODE"
MENU_IMAGE_MODE = "MENU_IMAGE_MODE"
MENU_SEARCH_MODE = "MENU_SEARCH_MODE"
MENU_REPORT_MODE = "MENU_REPORT_MODE"

async def _menu_handler_impl(event: P2ApplicationBotMenuV6):
    """
    处理飞书菜单点击事件 (Async Implementation)
    """
    from app.services.feishu_service import feishu_service
    logger.info(f"Received menu event: {event.event.event_key}")
    
    operator_id = event.event.operator.operator_id.open_id
    event_key = event.event.event_key
    
    # 清除旧的上下文数据 (图片描述、澄清问题上下文)
    await state_manager.delete_value(f"{operator_id}:image_desc")
    await state_manager.delete_value(f"{operator_id}:clarification_context")
    
    # 更新用户状态 (10分钟过期)
    await state_manager.set_user_mode(operator_id, event_key, ttl=600)
    
    if event_key == MENU_BASIC_MODE:
        logger.info(f"User {operator_id} switched to basic mode")
        await feishu_service.send_basic_mode_card(operator_id)
        
    elif event_key == MENU_IMAGE_MODE:
        logger.info(f"User {operator_id} switched to image mode")
        await feishu_service.send_image_mode_card(operator_id)
        
    elif event_key == MENU_SEARCH_MODE:
        logger.info(f"User {operator_id} switched to search mode")
        await feishu_service.send_search_mode_card(operator_id)
        
    elif event_key == MENU_REPORT_MODE:
        logger.info(f"User {operator_id} switched to report mode")
        await feishu_service.send_report_mode_card(operator_id)
        
    else:
        logger.info(f"Unknown menu key: {event_key}")
        await feishu_service.send_text(operator_id, "收到未知指令，正在开发中...")

def menu_handler(event: P2ApplicationBotMenuV6):
    """
    处理飞书菜单点击事件 (Sync Wrapper)
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_menu_handler_impl(event))
    except RuntimeError:
        logger.warning("No running loop found, creating new loop for menu_handler")
        asyncio.run(_menu_handler_impl(event))

def p2p_chat_entered_handler(event: P2ImChatAccessEventBotP2pChatEnteredV1):
    """
    处理机器人进入P2P单聊事件
    """
    logger.info(f"Bot entered P2P chat. Operator: {event.event.operator_id}, ChatID: {event.event.chat_id}")
    # 这里可以添加欢迎语逻辑，目前仅记录日志以消除 500 错误
    return
