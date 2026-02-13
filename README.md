# 飞书日报助手 (Feishu Daily Report Assistant)

<div align="center">

一个基于飞书机器人的智能日报管理系统，支持日报生成、查询、总结分析等功能。

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## ✨ 核心功能

### 📝 智能日报生成
- **AI 驱动优化**：使用 DeepSeek-V3.2 自动将简单工作记录扩展为专业技术日报
- **结构化输出**：包含"技术路径与思考逻辑"、"明日计划"等标准章节
- **上下文感知**：自动获取近期日报作为参考，保持连贯性

### 📊 多维度总结分析
- **日总结**：单天工作质量评估，包含评分（75-95分）和改进建议
- **周总结**：递归式对比分析，追踪一周工作趋势和成长轨迹
- **月总结**：压缩摘要优化，智能处理长上下文，生成月度工作总览

### 🔍 历史查询
- **灵活查询**：支持"查询昨天的日报"、"本周汇报统计"等自然语言查询
- **团队视图**：查看团队成员的汇报情况和统计数据

### 🤖 智能交互
- **双模式切换**：提示词优化模式 ↔ 日报周报模式
- **关键词识别**：快速响应"周总结"、"02-09总结"等命令
- **LLM 兜底**：支持复杂表达如"帮我看看这周的工作情况"

### ⏰ 自动化任务
- **定时同步**：每天 21:00 自动同步飞书日报并生成总结
- **周报触发**：每周日自动生成周总结
- **月报触发**：每月最后一天自动生成月总结

---

## 🚀 快速开始

### 环境要求

- Python 3.12+
- Redis (用于状态管理)
- 飞书企业应用权限

### 安装步骤

1. **克隆仓库**
   ```bash
   git clone https://github.com/your-username/prompt-optimizer.git
   cd prompt-optimizer
   ```

2. **创建虚拟环境**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # source .venv/bin/activate  # Linux/Mac
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **配置环境变量**
   ```bash
   cp .env.example .env
   ```
   
   编辑 `.env` 文件，填写以下配置：
   ```env
   # 飞书应用凭证
   FEISHU_APP_ID=your_app_id_here
   FEISHU_APP_SECRET=your_app_secret_here
   FEISHU_ENCRYPT_KEY=your_encrypt_key_here
   FEISHU_VERIFICATION_TOKEN=your_verification_token_here
   
   # Bitable 配置（用于存储总结）
   FEISHU_BITABLE_APP_TOKEN=your_bitable_app_token_here
   FEISHU_BITABLE_TABLE_ID=your_table_id_here
   
   # LLM API 配置
   OPENAI_API_KEY=your_api_key_here
   OPENAI_BASE_URL=https://api.siliconflow.cn/v1
   OPENAI_MODEL=deepseek-ai/DeepSeek-V3.2
   ```

5. **启动应用**
   ```bash
   # Windows
   .\run.bat
   
   # Linux/Mac
   python main.py
   ```

6. **配置飞书机器人**
   - 在飞书开放平台配置事件订阅 URL: `http://your-domain:8001/feishu/callback`
   - 订阅事件：`im.message.receive_v1`、`im.chat.access.bot_p2p_chat_entered_v1`
   - 配置机器人菜单（可选）

---

## 📖 使用指南

### 基础操作

1. **切换到日报模式**
   - 在飞书中向机器人发送任意消息
   - 点击菜单选择"日报周报模式"

2. **生成日报**
   ```
   今天完成了用户认证模块的开发
   明天计划进行单元测试
   ```

3. **查询历史**
   ```
   查询昨天的日报
   本周汇报统计
   ```

4. **生成总结**
   ```
   # 日总结
   02-09总结
   昨天总结
   
   # 周总结
   周总结
   上周总结
   
   # 月总结
   月总结
   1月总结
   ```

### 支持的关键词

| 总结类型 | 关键词示例 |
|---------|-----------|
| 📅 **日总结** | `日总结`、`今日总结`、`昨天总结`、`02-09总结` |
| 📊 **周总结** | `周总结`、`本周总结`、`上周总结`、`一周总结` |
| 📈 **月总结** | `月总结`、`本月总结`、`上月总结`、`1月总结` |

---

## 🏗️ 技术架构

```
prompt-optimizer/
├── app/
│   ├── controllers/      # API 控制器
│   ├── handlers/         # 飞书事件处理
│   ├── services/         # 业务逻辑层
│   │   ├── feishu_service.py         # 飞书 API 封装
│   │   ├── report_analysis_service.py # 总结分析服务
│   │   └── prompt_service.py          # 提示词优化服务
│   ├── core/             # 核心模块
│   │   ├── llm.py        # LLM 客户端
│   │   ├── prompts.py    # Prompt 模板
│   │   ├── config.py     # 配置管理
│   │   └── feishu.py     # 飞书事件分发
│   ├── repositories/     # 数据访问层
│   └── models/           # 数据模型
├── logs/                 # 日志目录
├── .env                  # 环境变量（不提交）
├── .env.example          # 环境变量模板
├── requirements.txt      # Python 依赖
└── main.py              # 应用入口
```

### 核心技术栈

- **Web 框架**: FastAPI + Uvicorn
- **LLM**: DeepSeek-V3.2 (via SiliconFlow)
- **飞书 SDK**: lark-oapi
- **数据库**: SQLite + SQLAlchemy
- **缓存**: Redis
- **定时任务**: APScheduler

---

## 🎯 核心特性详解

### 1. 混合意图识别

采用**关键词优先 + LLM 兜底**的双重策略：

```python
# 关键词快速匹配（毫秒级响应）
if re.search(r'(周总结|本周总结|上周总结)', input_text):
    intent_type = "weekly"

# LLM 处理复杂表达
else:
    intent = await recognize_summary_intent(input_text)
```

### 2. 递归式周总结

对比每日报告，生成趋势分析：

```
Day 1 vs Day 2 → 对比分析 A
Day 2 vs Day 3 → 对比分析 B
...
综合所有对比 → 周总结报告
```

### 3. 月总结上下文优化

使用抽象摘要压缩日报：

```
原始日报 (500字) → 压缩摘要 (≤100字) → 月度分析
```

---

## 🔧 配置说明

### 飞书应用权限

需要以下权限：
- `im:message` - 接收和发送消息
- `im:message.group_at_msg` - 群聊@消息
- `im:chat` - 获取会话信息
- `contact:user.base` - 获取用户信息
- `bitable:app` - 读写多维表格
- `report:report` - 读取日报数据

### 环境变量详解

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `PORT` | 服务端口 | `8001` |
| `FEISHU_APP_ID` | 飞书应用 ID | `cli_a9fdbc6dd2badcc9` |
| `FEISHU_BITABLE_APP_TOKEN` | 多维表格 Token | `VBmbbjQ3ZadpccshpZQc` |
| `OPENAI_API_KEY` | LLM API 密钥 | `sk-xxx` |
| `REDIS_URL` | Redis 连接地址 | `redis://localhost:6379/0` |

---

## 📊 评分标准

所有总结报告采用 **75-95 分**评分体系：

- **90-95分**: 卓越表现，技术深度和广度兼具
- **85-89分**: 优秀表现，有明显亮点
- **80-84分**: 良好表现（默认基准）
- **75-79分**: 合格表现，有改进空间
- **<75分**: 需要关注，存在明显问题

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 📝 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

- [FastAPI](https://fastapi.tiangolo.com/) - 现代化 Web 框架
- [飞书开放平台](https://open.feishu.cn/) - 企业协作平台
- [DeepSeek](https://www.deepseek.com/) - 强大的 LLM 模型
- [SiliconFlow](https://siliconflow.cn/) - LLM API 服务

---

## 📧 联系方式

如有问题或建议，欢迎通过以下方式联系：

- 提交 [Issue](https://github.com/your-username/prompt-optimizer/issues)
- 发送邮件至: your-email@example.com

---

<div align="center">

**⭐ 如果这个项目对你有帮助，请给一个 Star！**

Made with ❤️ by [Your Name]

</div>
