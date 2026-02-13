import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
import time
from app.services.report_analysis_service import ReportAnalysisService
from app.services.feishu_service import FeishuService
from app.core.config import settings
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Verify Real Settings Loaded
if not settings.FEISHU_BITABLE_APP_TOKEN or not settings.FEISHU_BITABLE_TABLE_ID:
    print("❌ Error: Real environment variables not loaded. Please check .env file.")
    exit(1)
else:
    print(f"✅ Loaded Real Config: AppToken={settings.FEISHU_BITABLE_APP_TOKEN[:5]}***, TableID={settings.FEISHU_BITABLE_TABLE_ID}")

class MockTask:
    def __init__(self, user_id, user_name, commit_time, form_contents=None):
        self.from_user_id = user_id
        self.from_user_name = user_name
        self.commit_time = commit_time
        self.rule_name = "日报"
        # Create dummy content
        if form_contents is None:
            class MockField:
                def __init__(self, name, value):
                    self.field_name = name
                    self.field_value = value
                    self.type = 'text'
            self.form_contents = [MockField("今日工作", f"测试内容 generated at {commit_time}")]
        else:
            self.form_contents = form_contents

class TestRealBitableSync(unittest.TestCase):
    def setUp(self):
        self.service = ReportAnalysisService()
        # Mock LLM Client to save cost/time, we focus on Bitable Sync
        self.service.llm_client = MagicMock()
        # 修改诊断建议以展示变化
        self.service.llm_client.chat = AsyncMock(return_value='{"advice": "✅ 诊断建议已更新 - 我们可以看到内容发生了变化！(Updated by Trae)", "score": 99}')
        
        # Test User Names
        # Use Real Bot ID for testing User Field logic
        self.test_user_a_id = "ou_9b9717cddeb73cbe049f7b854ba30581"
        self.test_user_a_name = "提示词优化助手" # Match the name in Bitable
        
        self.test_user_b = "TEST_USER_B"
        
    def tearDown(self):
        # Cleanup logic could go here, but we are testing the cleanup logic itself :)
        pass

    async def _clean_test_records(self, user_name, user_id=None):
        """Helper to clean records for a test user"""
        print(f"🧹 Cleaning up records for {user_name}...")
        # Search by name first (as fallback)
        filter_str = f'CurrentValue.[提交人] = "{user_name}"'
        
        # If we can filter by User ID in Bitable, that would be better, but "提交人" (Created By) is weird.
        # Let's search all and filter in memory to be safe for cleanup
        records = await FeishuService.search_bitable_records(
            settings.FEISHU_BITABLE_APP_TOKEN,
            settings.FEISHU_BITABLE_TABLE_ID,
            page_token=None # Get first page (usually enough for test cleanup)
        )
        
        if records:
            to_delete = []
            for r in records:
                fields = r.fields
                submitter = fields.get("提交人")
                
                # Check match
                is_match = False
                
                # Check against User Object (if submitter is a list/dict)
                if isinstance(submitter, list) and len(submitter) > 0:
                     if submitter[0].get('id') == user_id or submitter[0].get('name') == user_name:
                         is_match = True
                elif isinstance(submitter, dict):
                     if submitter.get('id') == user_id or submitter.get('name') == user_name:
                         is_match = True
                elif submitter == user_name:
                     is_match = True
                     
                # Also check "汇报人" field if it exists
                reporter = fields.get("汇报人")
                if reporter and isinstance(reporter, list) and len(reporter) > 0:
                     if reporter[0].get('id') == user_id:
                         is_match = True

                if is_match:
                    to_delete.append(r.record_id)

            if to_delete:
                print(f"   Found {len(to_delete)} records to delete.")
                for rid in to_delete:
                    await FeishuService.delete_bitable_record(
                        settings.FEISHU_BITABLE_APP_TOKEN,
                        settings.FEISHU_BITABLE_TABLE_ID,
                        rid
                    )
                print(f"   Deleted {len(to_delete)} records.")
            else:
                print("   No matching records found to delete.")
        else:
            print("   No records found in table.")

    @patch('app.services.report_analysis_service.FeishuService.get_report_tasks')
    @patch('app.services.report_analysis_service.FeishuService.batch_get_users')
    def test_real_bitable_operations(self, MockBatchGetUsers, MockGetReportTasks):
        """
        Integration Test against Real Bitable
        """
        async def run_async_test():
            # ==========================================================
            # Scenario 1: Local Filtering & Write (User A - Bot)
            # ==========================================================
            print("\n=== Scenario 1: Local Filtering & Write (User A - Bot) ===")
            
            # 1. Cleanup User A
            await self._clean_test_records(self.test_user_a_name, self.test_user_a_id)
            
            # 2. Setup Mock Tasks (3 tasks, same day)
            today = datetime.now().date()
            ts_base = int(datetime(today.year, today.month, today.day, 10, 0, 0).timestamp())
            
            # Use Real Bot ID
            task1 = MockTask(self.test_user_a_id, self.test_user_a_name, ts_base)          # 10:00
            task2 = MockTask(self.test_user_a_id, self.test_user_a_name, ts_base + 3600)   # 11:00 (Latest)
            task3 = MockTask(self.test_user_a_id, self.test_user_a_name, ts_base - 3600)   # 09:00
            
            MockGetReportTasks.return_value = [task1, task2, task3]
            MockBatchGetUsers.return_value = [] # No real users needed if we use ID directly
            
            # 3. Run Sync
            print("🚀 Running Sync for User A...")
            await self.service.sync_and_analyze(hours=24)
            
            # Wait for Bitable indexing (critical for Search after Write)
            print("⏳ Waiting 15s for Bitable indexing...")
            await asyncio.sleep(15)

            # 4. Verify in Bitable
            print("🔍 Verifying User A in Bitable...")
            # Search by date to be sure, then check user
            all_records = await FeishuService.search_bitable_records(
                settings.FEISHU_BITABLE_APP_TOKEN,
                settings.FEISHU_BITABLE_TABLE_ID,
                page_token=None
            )
            
            records = []
            if all_records:
                for r in all_records:
                    fields = r.fields
                    # Check 汇报人 (Reporter) - This is where we write the user_id
                    reporters = fields.get("汇报人", [])
                    is_match = False
                    if reporters and isinstance(reporters, list):
                        for rep in reporters:
                            if rep.get('id') == self.test_user_a_id:
                                is_match = True
                                break
                    
                    if is_match:
                        records.append(r)
            
            self.assertTrue(len(records) > 0, f"Expected records for User A ({self.test_user_a_name}), found 0")
            self.assertEqual(len(records), 1, f"Expected exactly 1 record for User A, found {len(records)}")
            
            # Verify Timestamp (should match 11:00)
            fields = records[0].fields
            saved_date = fields.get("汇报日期")
            expected_date = (ts_base + 3600) * 1000
            self.assertEqual(saved_date, expected_date, f"Timestamp mismatch! Expected {expected_date}, got {saved_date}")
            print("✅ Scenario 1 Passed: Only latest task preserved in Bitable.")

            # ==========================================================
            # Scenario 2: Delete-Then-Insert (User B - Fake Name)
            # ==========================================================
            # Note: For User B, we don't have a real ID, so we fallback to Name.
            # But "提交人" (Created By) will be Bot. "汇报人" will be empty.
            # So we rely on "提交人" == Bot AND we need to distinguish it?
            # Actually, since we can't write "TEST_USER_B" to "提交人" (System field),
            # and we can't write to "汇报人" (User field) without ID,
            # Scenario 2 is flawed in this environment unless we add a text field "姓名".
            #
            # BUT, the user requirement is "汇报人" (Reporter).
            # So we should assume real usage always has a User ID.
            # So let's re-run Scenario 1 again but with a different time to simulate "Overwrite".
            
            print("\n=== Scenario 2: Overwrite Logic (User A - Bot) ===")
            print("📝 Simulating a NEW sync with a LATER task for the SAME day...")
            
            # Setup New Mock Task (Later time: 13:00)
            task_new = MockTask(self.test_user_a_id, self.test_user_a_name, ts_base + 10800) # 13:00
            MockGetReportTasks.return_value = [task_new]
            
            # Run Sync again
            print("🚀 Running Sync Update for User A...")
            await self.service.sync_and_analyze(hours=24)
            
            print("⏳ Waiting 6s for Bitable indexing...")
            await asyncio.sleep(6)
            
            # Verify
            print("🔍 Verifying Update in Bitable...")
            all_records_post = await FeishuService.search_bitable_records(
                settings.FEISHU_BITABLE_APP_TOKEN,
                settings.FEISHU_BITABLE_TABLE_ID,
                page_token=None
            )
            
            records_post = []
            if all_records_post:
                for r in all_records_post:
                    fields = r.fields
                    reporters = fields.get("汇报人", [])
                    if reporters and isinstance(reporters, list):
                        if any(rep.get('id') == self.test_user_a_id for rep in reporters):
                            records_post.append(r)
                            
            self.assertEqual(len(records_post), 1, f"Expected 1 record after update, found {len(records_post)}")
            
            # Verify New Timestamp (should match 13:00)
            fields = records_post[0].fields
            saved_date = fields.get("汇报日期")
            expected_date = (ts_base + 10800) * 1000
            self.assertEqual(saved_date, expected_date, f"Timestamp mismatch! Expected {expected_date}, got {saved_date}")
            print("✅ Scenario 2 Passed: Record updated (overwrite logic confirmed).")

        asyncio.run(run_async_test())

if __name__ == '__main__':
    unittest.main()
