import time
import logging
import json
from datetime import datetime, timedelta
from app.services.feishu_service import FeishuService
from app.core.llm import LLMClient
from app.core.prompts import PROMPTS, PromptTemplate
from app.core.config import settings

logger = logging.getLogger(__name__)

class ReportAnalysisService:
    def __init__(self):
        self.llm_client = LLMClient()

    async def sync_and_analyze(self, hours: int = 24):
        """
        同步并分析飞书汇报
        :param hours: 查询过去多少小时的汇报
        """
        if not settings.FEISHU_BITABLE_APP_TOKEN or not settings.FEISHU_BITABLE_TABLE_ID:
            logger.error("Missing Bitable configuration (FEISHU_BITABLE_APP_TOKEN or FEISHU_BITABLE_TABLE_ID)")
            print("❌ 配置缺失: 请在 .env 中设置 FEISHU_BITABLE_APP_TOKEN 和 FEISHU_BITABLE_TABLE_ID")
            return

        # --- A. 设定查询时间范围 ---
        now = int(time.time())
        start_time = now - (hours * 3600)
        
        print(f"📥 正在从飞书汇报应用拉取数据 (过去 {hours} 小时)...")
        
        # --- B. Extract (提取) ---
        tasks = await FeishuService.get_report_tasks(start_time, now)
        
        if not tasks:
            print(f"📭 过去 {hours} 小时内没有新的汇报。")
            return

        print(f"✅ 获取到 {len(tasks)} 条汇报，开始处理...")
        
        # --- C. Delete-Then-Insert Preparation (删除后写入模式) ---
        # 1. 查询多维表格中已存在的记录，构建映射表，用于删除旧记录
        # 过滤条件: 汇报日期 >= start_time * 1000
        # 映射表: (user_id, date_str_yyyy_mm_dd) -> [record_ids]
        existing_map_by_id = {}
        existing_map_by_name = {}
        
        try:
            # 构造筛选条件：只查询开始时间之后的记录 (向前宽限1天以处理时区差异)
            search_start_time = (start_time - 86400) * 1000
            # 注意：日期筛选可能需要根据 Bitable 字段设置调整，此处假设为毫秒时间戳
            # 由于 Bitable 索引延迟导致刚写入的记录可能无法立即通过 Filter 查到，为确保去重逻辑可靠，暂时移除 Filter
            # filter_str = f'CurrentValue.[汇报日期] >= {search_start_time}'
            
            existing_records = await FeishuService.search_bitable_records(
                settings.FEISHU_BITABLE_APP_TOKEN,
                settings.FEISHU_BITABLE_TABLE_ID,
                # filter_str=filter_str
            )
            logger.info(f"Existing records search result count: {len(existing_records) if existing_records else 0}")
            
            if existing_records:
                for record in existing_records:
                    record_id = getattr(record, 'record_id', '')
                    fields = getattr(record, 'fields', {})
                    # logger.info(f"Checking record {record_id} for deduplication. Fields: {fields}")
                    
                    # 获取汇报日期
                    report_date = fields.get('汇报日期')
                    if not report_date:
                        # logger.warning(f"Record {record_id} missing '汇报日期', skipping.")
                        continue
                        
                    # 转换为 YYYY-MM-DD 字符串 (Bitable 存储的是毫秒)
                    dt = datetime.fromtimestamp(int(report_date) / 1000)
                    date_str = dt.strftime('%Y-%m-%d')
                    
                    # 1. 按汇报人 ID 匹配 (Person field)
                    reporters = fields.get('汇报人', [])
                    reporter_id = None
                    if reporters and isinstance(reporters, list):
                        reporter_id = reporters[0].get('id')
                    
                    if reporter_id:
                        key = (reporter_id, date_str)
                        if key not in existing_map_by_id:
                            existing_map_by_id[key] = []
                        existing_map_by_id[key].append(record_id)
                        # logger.info(f"Mapped record {record_id} to ID key {key}")
                    
                    # 2. 按提交人姓名匹配 (Fallback for Text/Person field)
                    submitter = fields.get('提交人')
                    submitter_name = None
                    if isinstance(submitter, list) and len(submitter) > 0:
                         submitter_name = submitter[0].get('name')
                    elif isinstance(submitter, dict):
                         submitter_name = submitter.get('name')
                    elif isinstance(submitter, str):
                         submitter_name = submitter
                         
                    if submitter_name:
                        key = (submitter_name, date_str)
                        if key not in existing_map_by_name:
                            existing_map_by_name[key] = []
                        existing_map_by_name[key].append(record_id)
                        # logger.info(f"Mapped record {record_id} to Name key {key}")
                        
                print(f"🔍 发现 {len(existing_records)} 条已有记录，将进行去重处理。")
                
        except Exception as e:
            logger.warning(f"Failed to fetch existing records for deduplication: {e}")
        
        # 预先批量获取用户信息
        user_ids = list(set([task.from_user_id for task in tasks if hasattr(task, 'from_user_id')]))
        user_map = {}
        if user_ids:
            users = await FeishuService.batch_get_users(user_ids)
            if users:
                for user in users:
                    user_map[user.user_id] = user.name

        # --- D. Filter Tasks (本地过滤: 每天每人只保留最新一条) ---
        # Map: (user_id, date_str) -> task
        filtered_tasks_map = {}
        
        for task in tasks:
            user_id = getattr(task, 'from_user_id', '')
            # 如果没有 user_id，尝试用名字作为 key (不太可靠，但作为 fallback)
            submitter_name = getattr(task, 'from_user_name', '') or user_map.get(user_id, "未知用户")
            
            commit_time = getattr(task, 'commit_time', now)
            dt = datetime.fromtimestamp(int(commit_time))
            date_str = dt.strftime('%Y-%m-%d')
            
            # 优先使用 user_id 组合键
            if user_id:
                key = (user_id, date_str)
            else:
                key = (submitter_name, date_str)
            
            # 比较 commit_time，保留最新的
            if key in filtered_tasks_map:
                existing_task = filtered_tasks_map[key]
                existing_time = getattr(existing_task, 'commit_time', 0)
                if int(commit_time) > int(existing_time):
                    filtered_tasks_map[key] = task
            else:
                filtered_tasks_map[key] = task
                
        final_tasks = list(filtered_tasks_map.values())
        print(f"🧹 过滤重复汇报后，剩余 {len(final_tasks)} 条待处理任务 (策略: 每天每人保留最新)。")

        for task in final_tasks:
            try:
                # 1. 提取基础信息
                user_id = getattr(task, 'from_user_id', '')
                submitter_name = getattr(task, 'from_user_name', '') or user_map.get(user_id, "未知用户")
                rule_name = getattr(task, 'rule_name', '未知汇报')
                commit_time = getattr(task, 'commit_time', now)
                
                # 计算 Date Key
                dt = datetime.fromtimestamp(int(commit_time))
                date_str = dt.strftime('%Y-%m-%d')
                
                # 2. Transform (转换) - 解析汇报内容
                content_text = self._parse_form_data(task)
                if not content_text:
                    print(f"⚠️ 跳过空汇报: {submitter_name}")
                    continue

                # 3. Transform (转换) - 确定报告类型
                report_type = "周报" if "周" in rule_name else "日报"
                
                # 4. Transform (转换) - AI 诊断
                print(f"🤖 正在 AI 诊断 {submitter_name} 的{report_type} ({date_str})...")
                ai_result = await self._call_ai_diagnosis(report_type, content_text)
                
                # 5. Delete Old Records (删除旧记录)
                records_to_delete = []
                
                # Check by User ID
                if user_id:
                    key_id = (user_id, date_str)
                    if key_id in existing_map_by_id:
                        records_to_delete.extend(existing_map_by_id[key_id])
                
                # Check by Name (Fallback or Additional)
                key_name = (submitter_name, date_str)
                if key_name in existing_map_by_name:
                    # 避免重复添加 (如果 ID 和 Name 查到了同一条)
                    for rid in existing_map_by_name[key_name]:
                        if rid not in records_to_delete:
                            records_to_delete.append(rid)
                            
                if records_to_delete:
                    print(f"🗑️ 发现 {submitter_name} 在 {date_str} 有 {len(records_to_delete)} 条旧记录，正在删除...")
                    for rid in records_to_delete:
                        await FeishuService.delete_bitable_record(
                            settings.FEISHU_BITABLE_APP_TOKEN,
                            settings.FEISHU_BITABLE_TABLE_ID,
                            rid
                        )
                
                # 6. Load (加载) - 写入新记录
                # 多维表格日期字段需要毫秒级时间戳
                date_val = int(commit_time) * 1000
                
                bitable_fields = {
                    "提交人": submitter_name,
                    "汇报人": [{"id": user_id}] if user_id else [],
                    "汇报日期": date_val,
                    "报告类型": report_type,
                    "汇报内容": content_text,
                    "AI诊断建议": ai_result.get("advice", "无建议"),
                    "评分": str(ai_result.get("score", 0)),
                    "状态": "已诊断"
                }
                
                success = await FeishuService.create_bitable_record(
                    settings.FEISHU_BITABLE_APP_TOKEN,
                    settings.FEISHU_BITABLE_TABLE_ID,
                    bitable_fields
                )
                
                if success:
                    print(f"✅ {submitter_name} 的数据已写入并诊断完成。")
                else:
                    print(f"❌ {submitter_name} 写入失败。")
                # ---------------------------------
                    
            except Exception as e:
                logger.error(f"Error processing task: {e}", exc_info=True)
                print(f"❌ 处理出错: {e}")

    def _parse_form_data(self, task) -> str:
        """
        解析 Task 对象中的 form_data
        """
        full_text = []
        # 注意：lark_oapi 返回的 task 对象结构可能包含 form_content 或 form_data
        # 这里假设 SDK 返回的是对象，我们需要遍历它的字段
        
        # 如果是 SDK 对象，通常 form_data 是一个 list
        # 修正: SDK 返回的字段名可能是 form_contents
        form_contents = getattr(task, 'form_contents', [])
        # 兼容旧逻辑
        if not form_contents:
            form_contents = getattr(task, 'form_data', [])

        if not form_contents:
             return ""

        for field in form_contents:
            # 兼容不同 SDK 版本的字段名
            name = getattr(field, 'field_name', getattr(field, 'name', ''))
            value = getattr(field, 'field_value', getattr(field, 'value', ''))
            
            # 兼容 value 可能为 None 的情况
            if value is None:
                # 尝试 type 为 text 的情况
                if getattr(field, 'type', '') == 'text':
                     value = getattr(field, 'text_value', '')

            if value:
                full_text.append(f"【{name}】: {value}")
        
        return "\n".join(full_text)

    async def _call_ai_diagnosis(self, report_type: str, content: str) -> dict:
        """
        调用 LLM 进行诊断
        """
        prompt = PROMPTS[PromptTemplate.REPORT_DIAGNOSIS].format(
            report_type=report_type,
            content=content
        )
        
        try:
            # 使用 JSON 模式 (如果 LLMClient 支持，否则解析文本)
            # 这里假设 LLMClient 返回的是字符串，我们尝试解析 JSON
            messages = [{"role": "user", "content": prompt}]
            response = await self.llm_client.chat(messages)
            
            # 清理 Markdown 代码块 (```json ... ```)
            if response.startswith("```"):
                lines = response.split("\n")
                if lines[0].strip().startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
                response = "\n".join(lines)
                
            return json.loads(response)
            
        except Exception as e:
            logger.error(f"AI diagnosis failed: {e}")
            return {"advice": "AI 诊断失败，请检查日志。", "score": 0}

    async def _prepare_weekly_data(self, start_time: int, end_time: int) -> dict:
        """
        拉取并整理一周的日报数据，按用户分组并按日期排序
        :param start_time: 开始时间戳（秒）
        :param end_time: 结束时间戳（秒）
        :return: {user_name: {'user_id': str, 'reports': [(date_str, content_text), ...]}, ...}
        """
        tasks = await FeishuService.get_report_tasks(start_time, end_time)
        
        if not tasks:
            return {}

        # 批量获取用户信息
        user_ids = list(set([task.from_user_id for task in tasks if hasattr(task, 'from_user_id')]))
        user_map = {}
        if user_ids:
            users = await FeishuService.batch_get_users(user_ids)
            if users:
                for user in users:
                    user_map[user.user_id] = user.name

        # 按 (user_id, date) 分组，每人每天只保留最新一条
        filtered_map = {}  # (user_id, date_str) -> (commit_time, task, user_name, user_id)
        
        for task in tasks:
            user_id = getattr(task, 'from_user_id', '')
            user_name = getattr(task, 'from_user_name', '') or user_map.get(user_id, "未知用户")
            commit_time = getattr(task, 'commit_time', 0)
            dt = datetime.fromtimestamp(int(commit_time))
            date_str = dt.strftime('%Y-%m-%d')
            
            key = (user_id or user_name, date_str)
            
            if key in filtered_map:
                if int(commit_time) > filtered_map[key][0]:
                    filtered_map[key] = (int(commit_time), task, user_name, user_id)
            else:
                filtered_map[key] = (int(commit_time), task, user_name, user_id)

        # 按用户分组，按日期排序
        user_reports = {}  # user_name -> {'user_id': str, 'reports': [(date_str, content_text), ...]}
        
        for (uid_or_name, date_str), (_, task, user_name, user_id) in filtered_map.items():
            content_text = self._parse_form_data(task)
            if not content_text:
                continue
            
            if user_name not in user_reports:
                user_reports[user_name] = {'user_id': user_id, 'reports': []}
            user_reports[user_name]['reports'].append((date_str, content_text))

        # 按日期排序
        for user_name in user_reports:
            user_reports[user_name]['reports'].sort(key=lambda x: x[0])

        return user_reports

    def _format_weekly_reports(self, reports: list[tuple[str, str]]) -> str:
        """
        将一周的日报列表格式化为 LLM 输入文本
        """
        parts = []
        for i, (date_str, content) in enumerate(reports, 1):
            parts.append(f"--- 第{i}天: {date_str} ---")
            parts.append(content)
            parts.append("")
        return "\n".join(parts)

    @staticmethod
    def _extract_summary_and_score(full_content: str) -> tuple:
        """
        从 LLM 生成的 Markdown 分析报告中提取摘要和评分
        :param full_content: 完整的 Markdown 分析文本
        :return: (summary_text, score)
        """
        import re
        
        # 提取评分：匹配 "周度评分: XX/100" 或 "评分: XX/100"
        score = 0
        score_match = re.search(r'评分[：:]\s*(\d+)\s*/\s*100', full_content)
        if score_match:
            score = int(score_match.group(1))
        
        # 提取摘要：匹配 "## 摘要" 后面的内容
        summary = ""
        summary_match = re.search(r'##\s*摘要\s*\n([\s\S]*?)(?:\n##|\n#|\Z)', full_content)
        if summary_match:
            summary = summary_match.group(1).strip()
        
        # 如果没有提取到摘要，用前200字作为摘要
        if not summary:
            # 去掉标题行，取前200字
            lines = [l for l in full_content.split('\n') if not l.startswith('#')]
            summary = '\n'.join(lines)[:200].strip()
            if len(full_content) > 200:
                summary += "..."
        
        return summary, score

    async def _save_summary_to_bitable(self, user_name: str, user_id: str, date_range: str, 
                                       full_content: str, summary: str, score: int, report_type: str = "周总结"):
        """
        将周/日/月总结结果写入 Bitable
        :param report_type: "周总结", "日总结", 或 "月总结"
        """
        if not settings.FEISHU_BITABLE_APP_TOKEN or not settings.FEISHU_BITABLE_TABLE_ID:
            logger.warning("Missing Bitable configuration, skipping write.")
            return False

        # 当前时间戳（毫秒）作为汇报日期
        date_val = int(time.time()) * 1000
        
        bitable_fields = {
            "提交人": user_name,
            "汇报人": [{"id": user_id}] if user_id else [],
            "汇报日期": date_val,
            "报告类型": report_type,
            "汇报内容": full_content,
            "AI诊断建议": summary,
            "评分": str(score),
            "状态": "已总结",
            "分析周期": date_range
        }
        
        try:
            success = await FeishuService.create_bitable_record(
                settings.FEISHU_BITABLE_APP_TOKEN,
                settings.FEISHU_BITABLE_TABLE_ID,
                bitable_fields
            )
            if success:
                logger.info(f"✅ {user_name} 的{report_type}已写入 Bitable")
            else:
                logger.error(f"❌ {user_name} 的{report_type}写入 Bitable 失败")
            return success
        except Exception as e:
            logger.error(f"Error saving {report_type} to Bitable: {e}", exc_info=True)
            return False

    async def weekly_recursive_summary_stream(self, start_time: int, end_time: int, 
                                                target_user_name: str = None,
                                                save_to_bitable: bool = True):
        """
        流式生成一周递归式进步总结
        :param start_time: 开始时间戳（秒）
        :param end_time: 结束时间戳（秒）
        :param target_user_name: 指定用户名（可选）
        :param save_to_bitable: 是否在完成后写入 Bitable
        :yields: 流式文本块（最后一个 yield 额外附带完整内容）
        """
        user_reports = await self._prepare_weekly_data(start_time, end_time)
        
        if not user_reports:
            yield "⚠️ 该时间范围内没有找到日报数据。"
            return

        if target_user_name:
            matched = {k: v for k, v in user_reports.items() if target_user_name in k}
            if not matched:
                yield f"⚠️ 未找到用户 {target_user_name} 的日报数据。"
                return
            user_reports = matched

        user_list = list(user_reports.items())
        for idx, (user_name, user_data) in enumerate(user_list):
            if idx > 0:
                yield "\n\n---\n\n"

            user_id = user_data['user_id']
            reports = user_data['reports']
            date_range = f"{reports[0][0]} 至 {reports[-1][0]}" if len(reports) > 1 else reports[0][0]
            daily_reports_text = self._format_weekly_reports(reports)
            
            prompt = PROMPTS[PromptTemplate.WEEKLY_RECURSIVE_SUMMARY].format(
                user_name=user_name,
                date_range=date_range,
                daily_reports=daily_reports_text
            )
            
            messages = [{"role": "user", "content": prompt}]
            user_full_content = ""
            
            try:
                async for chunk in self.llm_client.chat_stream(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=4000
                ):
                    user_full_content += chunk
                    yield chunk
                
                # 流式结束后写入 Bitable
                if save_to_bitable and user_full_content:
                    summary, score = self._extract_summary_and_score(user_full_content)
                    # 判断是周总结还是日总结（根据日期范围）
                    is_single_day = len(reports) == 1
                    report_type = "日总结" if is_single_day else "周总结"
                    await self._save_summary_to_bitable(
                        user_name, user_id, date_range, user_full_content, summary, score, report_type
                    )
            except Exception as e:
                logger.error(f"Weekly summary stream failed for {user_name}: {e}")
                yield f"\n\n❌ 生成 {user_name} 的周总结时出错: {str(e)}"

    async def weekly_summary_and_save(self, start_time: int, end_time: int):
        """
        非流式生成周总结并写入 Bitable（供定时任务调用）
        :param start_time: 开始时间戳（秒）
        :param end_time: 结束时间戳（秒）
        :return: 处理的用户数量
        """
        user_reports = await self._prepare_weekly_data(start_time, end_time)
        
        if not user_reports:
            logger.info("No report data found for weekly summary.")
            return 0

        processed_count = 0
        for user_name, user_data in user_reports.items():
            user_id = user_data['user_id']
            reports = user_data['reports']
            date_range = f"{reports[0][0]} 至 {reports[-1][0]}" if len(reports) > 1 else reports[0][0]
            daily_reports_text = self._format_weekly_reports(reports)
            
            prompt = PROMPTS[PromptTemplate.WEEKLY_RECURSIVE_SUMMARY].format(
                user_name=user_name,
                date_range=date_range,
                daily_reports=daily_reports_text
            )
            
            messages = [{"role": "user", "content": prompt}]
            
            try:
                response = await self.llm_client.chat(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=4000
                )
                
                if response:
                    summary, score = self._extract_summary_and_score(response)
                    # 判断是周总结还是日总结
                    is_single_day = len(reports) == 1
                    report_type = "日总结" if is_single_day else "周总结"
                    success = await self._save_summary_to_bitable(
                        user_name, user_id, date_range, response, summary, score, report_type
                    )
                    if success:
                        processed_count += 1
                        logger.info(f"Weekly summary for {user_name}: score={score}")
                        
            except Exception as e:
                logger.error(f"Weekly summary failed for {user_name}: {e}", exc_info=True)

        return processed_count

    # ===================== 意图识别 =====================

    async def recognize_summary_intent(self, user_input: str) -> dict:
        """
        使用 LLM 识别用户输入中的总结意图
        :return: {"type": "daily|weekly|monthly|none", "date_info": "..."}
        """
        current_date = datetime.now().strftime('%Y-%m-%d')
        prompt = PROMPTS[PromptTemplate.SUMMARY_INTENT_RECOGNITION].format(
            user_input=user_input,
            current_date=current_date
        )
        
        messages = [{"role": "user", "content": prompt}]
        
        try:
            response = await self.llm_client.chat(
                messages=messages,
                temperature=0.1,
                max_tokens=200
            )
            
            if response:
                # 清理可能的 markdown 代码块包裹和其他格式
                cleaned = response.strip()
                
                # 移除代码块标记 (```json 或 ```)
                if cleaned.startswith("```"):
                    # 找到第一个换行符后的内容
                    lines = cleaned.split("\n")
                    if len(lines) > 1:
                        cleaned = "\n".join(lines[1:])
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
                    cleaned = cleaned.strip()
                
                # 尝试从文本中提取JSON对象
                import re
                json_match = re.search(r'\{[^}]+\}', cleaned)
                if json_match:
                    cleaned = json_match.group(0)
                
                result = json.loads(cleaned)
                if isinstance(result, dict) and "type" in result:
                    logger.info(f"Intent recognized: {result}")
                    return result
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Intent recognition failed: {e}, response: {response[:200] if response else 'None'}, input: {user_input}")
        
        return {"type": "none", "date_info": ""}

    @staticmethod
    def parse_date_range(intent_type: str, date_info: str) -> tuple:
        """
        根据意图识别结果计算时间范围
        :return: (start_ts, end_ts, date_range_desc)
        """
        now = datetime.now()
        
        if intent_type == "daily":
            # 解析具体日期
            target_date = now
            
            if "昨天" in date_info or "昨日" in date_info:
                target_date = now - timedelta(days=1)
            elif "前天" in date_info:
                target_date = now - timedelta(days=2)
            elif "今天" in date_info or "今日" in date_info or not date_info:
                target_date = now
            else:
                # 尝试解析 MM-DD 或 M月D日 格式
                import re
                m = re.search(r'(\d{1,2})[月\-/](\d{1,2})', date_info)
                if m:
                    month = int(m.group(1))
                    day = int(m.group(2))
                    year = now.year
                    try:
                        target_date = datetime(year, month, day)
                    except ValueError:
                        pass
            
            # 当天 00:00:00 到 23:59:59
            day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start.replace(hour=23, minute=59, second=59)
            date_desc = day_start.strftime('%Y-%m-%d')
            return int(day_start.timestamp()), int(day_end.timestamp()), date_desc

        elif intent_type == "weekly":
            days_since_monday = now.weekday()
            
            if "上周" in date_info:
                monday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday + 7)
                sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
                date_desc = f"{monday.strftime('%Y-%m-%d')} 至 {sunday.strftime('%Y-%m-%d')} (上周)"
                return int(monday.timestamp()), int(sunday.timestamp()), date_desc
            else:
                monday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
                date_desc = f"{monday.strftime('%Y-%m-%d')} 至 {now.strftime('%Y-%m-%d')} (本周)"
                return int(monday.timestamp()), int(now.timestamp()), date_desc

        elif intent_type == "monthly":
            import re
            import calendar
            
            if "上月" in date_info or "上个月" in date_info:
                if now.month == 1:
                    target_year, target_month = now.year - 1, 12
                else:
                    target_year, target_month = now.year, now.month - 1
            else:
                # 尝试解析 "X月"
                m = re.search(r'(\d{1,2})\s*月', date_info)
                if m:
                    target_month = int(m.group(1))
                    target_year = now.year
                    # 如果指定的月份大于当前月，可能指去年
                    if target_month > now.month:
                        target_year -= 1
                else:
                    # 默认本月
                    target_year, target_month = now.year, now.month
            
            _, last_day = calendar.monthrange(target_year, target_month)
            month_start = datetime(target_year, target_month, 1, 0, 0, 0)
            month_end = datetime(target_year, target_month, last_day, 23, 59, 59)
            date_desc = f"{month_start.strftime('%Y-%m-%d')} 至 {month_end.strftime('%Y-%m-%d')} ({target_month}月)"
            return int(month_start.timestamp()), int(month_end.timestamp()), date_desc
        
        # fallback
        return 0, 0, ""

    # ===================== 日总结 =====================

    async def daily_summary_stream(self, start_time: int, end_time: int,
                                     save_to_bitable: bool = True):
        """
        流式生成日总结（单天工作评估）
        """
        user_reports = await self._prepare_weekly_data(start_time, end_time)
        
        if not user_reports:
            yield "⚠️ 该日期没有找到日报数据。"
            return

        date_str = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d')
        
        for user_name, user_data in user_reports.items():
            user_id = user_data['user_id']
            reports = user_data['reports']
            
            # 日总结只取当天的数据
            daily_content = "\n".join([content for _, content in reports])
            
            prompt = PROMPTS[PromptTemplate.DAILY_SUMMARY].format(
                user_name=user_name,
                date_str=date_str,
                daily_content=daily_content
            )
            
            messages = [{"role": "user", "content": prompt}]
            user_full_content = ""
            
            try:
                async for chunk in self.llm_client.chat_stream(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=3000
                ):
                    user_full_content += chunk
                    yield chunk
                
                if save_to_bitable and user_full_content:
                    summary, score = self._extract_summary_and_score(user_full_content)
                    await self._save_summary_to_bitable(
                        user_name, user_id, date_str, user_full_content, 
                        summary, score, "日总结"
                    )
            except Exception as e:
                logger.error(f"Daily summary stream failed for {user_name}: {e}")
                yield f"\n\n❌ 生成 {user_name} 的日总结时出错: {str(e)}"

    # ===================== 月总结 =====================

    async def _compress_daily_for_monthly(self, user_reports: dict) -> dict:
        """
        将每日日报压缩为 ≤100 字的摘要（用于月总结上下文优化）
        :param user_reports: {user_name: {'user_id': str, 'reports': [(date_str, content), ...]}}
        :return: {user_name: {'user_id': str, 'summaries': [(date_str, summary_text), ...]}}
        """
        compressed = {}
        
        for user_name, user_data in user_reports.items():
            user_id = user_data['user_id']
            summaries = []
            
            for date_str, content in user_data['reports']:
                # 尝试用简短 prompt 压缩
                try:
                    compress_prompt = f"请用不超过100个中文字符概括以下工作日报的核心内容,只输出概括文字,不要任何前缀:\n\n{content}"
                    messages = [{"role": "user", "content": compress_prompt}]
                    summary = await self.llm_client.chat(
                        messages=messages,
                        temperature=0.3,
                        max_tokens=200
                    )
                    if summary:
                        # 确保不超过100字
                        summary = summary.strip()[:100]
                    else:
                        summary = content[:100] + "..." if len(content) > 100 else content
                except Exception:
                    summary = content[:100] + "..." if len(content) > 100 else content
                
                summaries.append((date_str, summary))
            
            compressed[user_name] = {'user_id': user_id, 'summaries': summaries}
        
        return compressed

    async def monthly_summary_stream(self, start_time: int, end_time: int,
                                       save_to_bitable: bool = True):
        """
        流式生成月总结（基于压缩的每日摘要）
        """
        user_reports = await self._prepare_weekly_data(start_time, end_time)
        
        if not user_reports:
            yield "⚠️ 该月份没有找到日报数据。"
            return

        # Step 1: 压缩每日日报为摘要
        yield "📝 正在整理月度数据...\n\n"
        compressed_data = await self._compress_daily_for_monthly(user_reports)
        
        month_range = f"{datetime.fromtimestamp(start_time).strftime('%Y-%m-%d')} 至 {datetime.fromtimestamp(end_time).strftime('%Y-%m-%d')}"
        
        for user_name, user_data in compressed_data.items():
            user_id = user_data['user_id']
            summaries = user_data['summaries']
            
            # 格式化每日摘要
            daily_summaries_text = "\n".join([
                f"- {date_str}: {summary}" for date_str, summary in summaries
            ])
            
            prompt = PROMPTS[PromptTemplate.MONTHLY_SUMMARY].format(
                user_name=user_name,
                month_range=month_range,
                daily_summaries=daily_summaries_text
            )
            
            messages = [{"role": "user", "content": prompt}]
            user_full_content = ""
            
            try:
                async for chunk in self.llm_client.chat_stream(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=4000
                ):
                    user_full_content += chunk
                    yield chunk

                # 写入 Bitable
                if save_to_bitable and user_full_content:
                    summary, score = self._extract_summary_and_score(user_full_content)
                    await self._save_summary_to_bitable(
                        user_name, user_id, month_range, user_full_content, 
                        summary, score, "月总结"
                    )

            except Exception as e:
                logger.error(f"Monthly summary stream failed for {user_name}: {e}")
                yield f"\n\n❌ 生成 {user_name} 的月总结时出错: {str(e)}"


    # ===================== 非流式（定时任务用） =====================

    async def daily_summary_and_save(self, start_time: int, end_time: int):
        """非流式日总结并写入 Bitable（定时任务用）"""
        user_reports = await self._prepare_weekly_data(start_time, end_time)
        if not user_reports:
            logger.info("No report data found for daily summary.")
            return 0

        date_str = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d')
        processed_count = 0
        
        for user_name, user_data in user_reports.items():
            user_id = user_data['user_id']
            reports = user_data['reports']
            daily_content = "\n".join([content for _, content in reports])
            
            prompt = PROMPTS[PromptTemplate.DAILY_SUMMARY].format(
                user_name=user_name,
                date_str=date_str,
                daily_content=daily_content
            )
            messages = [{"role": "user", "content": prompt}]
            
            try:
                response = await self.llm_client.chat(
                    messages=messages, temperature=0.7, max_tokens=3000
                )
                if response:
                    summary, score = self._extract_summary_and_score(response)
                    success = await self._save_summary_to_bitable(
                        user_name, user_id, date_str, response, summary, score, "日总结"
                    )
                    if success:
                        processed_count += 1
            except Exception as e:
                logger.error(f"Daily summary failed for {user_name}: {e}", exc_info=True)
        
        return processed_count

    async def monthly_summary_and_save(self, start_time: int, end_time: int):
        """非流式月总结并写入 Bitable（定时任务用）"""
        user_reports = await self._prepare_weekly_data(start_time, end_time)
        if not user_reports:
            logger.info("No report data found for monthly summary.")
            return 0

        compressed_data = await self._compress_daily_for_monthly(user_reports)
        month_range = f"{datetime.fromtimestamp(start_time).strftime('%Y-%m-%d')} 至 {datetime.fromtimestamp(end_time).strftime('%Y-%m-%d')}"
        processed_count = 0
        
        for user_name, user_data in compressed_data.items():
            user_id = user_data['user_id']
            summaries = user_data['summaries']
            daily_summaries_text = "\n".join([
                f"- {date_str}: {summary}" for date_str, summary in summaries
            ])
            
            prompt = PROMPTS[PromptTemplate.MONTHLY_SUMMARY].format(
                user_name=user_name,
                month_range=month_range,
                daily_summaries=daily_summaries_text
            )
            messages = [{"role": "user", "content": prompt}]
            
            try:
                response = await self.llm_client.chat(
                    messages=messages, temperature=0.7, max_tokens=4000
                )
                if response:
                    summary, score = self._extract_summary_and_score(response)
                    success = await self._save_summary_to_bitable(
                        user_name, user_id, month_range, response, summary, score, "月总结"
                    )
                    if success:
                        processed_count += 1
            except Exception as e:
                logger.error(f"Monthly summary failed for {user_name}: {e}", exc_info=True)
        
        return processed_count
