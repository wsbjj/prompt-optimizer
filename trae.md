# 项目需求汇总 (Trae AI 识别用)

## 1. 项目概述
本项目是将原有的 TypeScript + Vite 前端 Prompt Optimizer 工具重构为 Python 后端服务，核心目标是提供飞书机器人（Bot）后端，利用大模型（LLM）能力对用户输入的提示词进行优化。

## 2. 技术栈
- **语言**: Python 3.11+
- **Web 框架**: FastAPI
- **飞书 SDK**: lark-oapi (v1.2.0+)
- **LLM SDK**: openai (AsyncOpenAI)
- **数据库**: SQLite (aiosqlite) + SQLAlchemy (Async ORM)
- **配置管理**: pydantic-settings
- **依赖管理**: requirements.txt

## 3. 架构设计 (SpringBoot 三层架构风格)
- **Controllers (app/controllers)**: 处理 HTTP 请求，路由分发。
  - `feishu_controller.py`: 处理飞书 Webhook 回调和事件。
- **Services (app/services)**: 核心业务逻辑。
  - `prompt_service.py`: 提示词优化逻辑。
  - `feishu_service.py`: 飞书消息发送、卡片构建。
- **Repositories (app/repositories)**: 数据持久化。
  - `prompt_repository.py`: 提示词日志存储。
- **Models (app/models)**: 数据库实体。
  - `prompt_log.py`: 提示词记录表。
- **Schemas (app/schemas)**: 数据传输对象 (Pydantic)。

## 4. 核心功能与接口
### 4.1 飞书 Webhook
- **路径**: 
  - `/feishu/event`: 接收飞书事件订阅（统一入口）。
  - `/feishu/callback`: 接收飞书回调（兼容路径）。
- **功能**:
  - 自动处理 URL Verification (Challenge)。
  - 签名验证 (X-Lark-Signature) 和解密 (使用 lark-oapi EventDispatcherHandler)。
  - 异步分发消息事件 (im.message.receive_v1)。

### 4.2 提示词优化
- **输入**: 用户发送的文本消息。
- **触发指令**:
  - `sys:` 或 `系统:` -> 优化系统提示词 (System Prompt)。
  - `pro:` 或 `专业:` -> 优化为专业版提示词。
  - 默认 -> 基础用户提示词优化。
- **输出**: 优化后的提示词文本，通过飞书回复给用户。

### 4.3 机器人菜单配置
- **配置路径**: 飞书开发者后台 -> 应用功能 -> 机器人 -> 菜单配置
- **菜单项 1**:
  - 名称: 基础模式
  - 响应动作: 推送事件
  - 事件 ID: `MENU_BASIC_MODE`
- **菜单项 2**:
  - 名称: 图片模式
  - 响应动作: 推送事件
  - 事件 ID: `MENU_IMAGE_MODE`
- **菜单项 3**:
  - 名称: 关键词检索
  - 响应动作: 推送事件
  - 事件 ID: `MENU_SEARCH_MODE`
- **菜单项 4**:
  - 名称: 日报周报总结
  - 响应动作: 推送事件
  - 事件 ID: `MENU_REPORT_MODE`
- **注意**: 事件 ID 必须与代码中的 `MENU_BASIC_MODE`、`MENU_IMAGE_MODE`、`MENU_SEARCH_MODE` 等常量保持一致。

## 5. 开发规范
- **语言**: 代码注释和文档字符串全部使用 **中文**。
- **类型提示**: 所有函数必须包含参数和返回值的 Type Hinting。
- **文档**: 每个函数必须包含详细的 Docstring 介绍功能。
- **环境**: 使用 `.venv` 虚拟环境管理依赖。

## 6. 当前状态
- 已完成基础架构搭建和核心代码迁移。
- 已实现飞书事件接收和分发逻辑。
- 已集成 OpenAI SDK 进行提示词优化。
- 数据库层已就绪。
- 已添加飞书机器人菜单事件处理。
