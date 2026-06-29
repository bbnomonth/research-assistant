# 后端运行说明

当前阶段已实现：

- SQLite 项目、会话、消息和模型调用日志；
- LLM 意图分类 + 关键词回退，自动路由到五种工作模式；
- 普通研究问答；
- 阿里云百炼 Qwen 流式调用；
- arXiv 真实文献检索与项目内题录持久化；
- PDF 上传、前 60 页文本解析和 FTS5 原文证据搜索；
- Tesseract OCR 调用边界；
- 基于已解析证据的论文快速分析、Artifact 持久化和 Markdown 导出；
- 最多三篇论文的证据绑定对比；
- 选题导师（苏格拉底式提问 + 选题方案 Artifact）；
- 论文框架搭建导师（苏格拉底式逐轮提问 + 整理为结构化卡片 Artifact）；
- 基于显式 `paper_id` 的多轮引导式精读与阅读成果沉淀；
- arXiv PDF 下载、大小限制、解析和证据索引；
- 项目、会话和历史消息管理接口；
- 任务取消、重试和启动中断恢复；
- 脱敏运行设置与模型、OCR、存储诊断；
- 结构化模型输出的一次修复和统一脱敏调用日志；
- SSE 聊天接口；
- 健康检查接口。

五种聊天模式均已接入实际工作流。论文精读不会自动猜测目标论文，请求必须显式传入 `paper_id`。

## 1. 安装依赖

在项目根目录运行：

```powershell
python -m pip install -e 'backend[test]'
```

## 2. 配置百炼 API Key

复制配置模板：

```powershell
Copy-Item backend/.env.example backend/.env
```

打开 `backend/.env`，只替换下面的占位符：

```dotenv
DASHSCOPE_API_KEY=replace-with-your-api-key
```

不要把真实 Key：

- 发到聊天中；
- 写进 `.env.example`；
- 放入源代码；
- 截图公开；
- 提交到 Git。

`backend/.env`、SQLite、上传论文、解析内容和日志均已加入 Git 忽略规则。

## 3. 启动服务

在项目根目录运行：

```powershell
python -m uvicorn research_agent.main:app --app-dir backend/src --host 127.0.0.1 --port 8000 --reload
```

访问：

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

正确配置 Key 后，健康检查中的 `model_configured` 为 `true`。
配置 Tesseract 后，健康检查中的 `ocr_configured` 为 `true`。

## 4. 流式聊天

接口：

```text
POST /api/chat/stream
Content-Type: application/json
```

请求示例：

```json
{
  "content": "什么是混合整数规划？"
}
```

响应为 SSE，主要事件包括：

- `mode`：当前工作模式；
- `metadata`：项目与会话 ID；
- `stage`：检索式生成、arXiv 检索、推荐和保存进度；
- `search_results`：真实候选论文和推荐论文；
- `artifact`：选题、框架、分析或对比产生的可编辑成果；
- `token`：模型流式文本；
- `done`：完整回答；
- `error`：脱敏错误信息。

文献发现每次最多向 arXiv 请求 20 篇候选。系统遵守 arXiv 的请求节流要求，不并发轰炸接口；文献发现阶段只读取题录和摘要，不下载 PDF。

`search_results` 中题名、作者、摘要、日期、链接和 arXiv ID 均来自 arXiv。Qwen 只负责生成英文检索式、筛选候选和解释推荐理由。

选题指导和论文框架搭建均通过聊天 SSE 接口完成。当前产品不再保留独立的“研究诊断”入口；选题相关能力统一由选题导师承载，框架相关能力统一由论文框架搭建导师承载。

## 5. 运行测试

测试不会调用真实模型：

```powershell
python -m pytest backend/tests -q
```

## 6. 数据位置

默认数据位置：

```text
data/app.sqlite3
data/uploads/
```

这些内容只保存在本机，不进入版本控制。模型请求会将当前问题及必要的最近对话发送给阿里云百炼；后续论文功能只发送当前任务必要的文本片段或截图。

## 7. PDF 上传与证据检索

上传接口：

```text
POST /api/papers/upload
multipart/form-data: file=<PDF>
```

限制：

- 仅支持 `.pdf`；
- 最大 10 MB；
- 只解析前 60 页；
- 优先使用 PDF 文本层；
- 配置 `TESSERACT_EXECUTABLE` 后，文本过少或扫描页会自动使用 OCR fallback。

证据检索接口：

```text
GET /api/papers/{paper_id}/evidence?q=machine%20learning
```

返回内容包括：

- 文本块 ID；
- 页码；
- 章节字段；
- 原文片段；
- 是否 OCR。

任务状态接口：

```text
GET /api/tasks/{task_id}
```

OCR 配置项：

```dotenv
TESSERACT_EXECUTABLE=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_LANGUAGE=chi_sim+eng
```

OCR 结果会以 `is_ocr=true` 写入证据块。若未配置 Tesseract，普通文本 PDF 仍可解析，扫描 PDF 可能没有可检索正文。

## 8. 论文快速分析与成果导出

快速分析接口：

```text
POST /api/papers/{paper_id}/quick-analysis
```

该接口只使用数据库中已解析的论文文本块作为证据，调用模型生成结构化文献卡片，保存为 Artifact，并返回：

- Artifact ID；
- 成果标题；
- 使用到的证据页码。

论文对比接口：

```text
POST /api/papers/compare
Content-Type: application/json
```

请求示例：

```json
{
  "paper_ids": ["paper-id-1", "paper-id-2"]
}
```

限制：

- 需要 2 到 3 篇论文；
- 论文必须属于同一项目；
- 只使用数据库中已解析的 evidence chunks；
- 返回 Artifact ID 和每篇论文使用到的证据页码；
- 对比成果类型为 `paper_comparison`，可通过 Artifact 接口继续查看、编辑和导出。

Markdown 导出接口：

```text
GET /api/artifacts/{artifact_id}/markdown
```

Artifact 详情接口：

```text
GET /api/artifacts/{artifact_id}
```

项目成果列表接口：

```text
GET /api/projects/{project_id}/artifacts
```

Artifact 编辑接口：

```text
PATCH /api/artifacts/{artifact_id}
Content-Type: application/json
```

可更新 `title`、`content` 和 `markdown`。Markdown 导出不会再次调用模型，只读取已持久化的 Artifact Markdown。未配置模型时，快速分析接口会返回 503，不会静默伪造分析结果。

## 9. 引导式精读

引导式精读继续使用聊天 SSE 接口，请求示例：

```json
{
  "content": "这篇论文主要研究车辆路径优化问题。",
  "project_id": "project-id",
  "session_id": "session-id",
  "paper_id": "paper-id",
  "mode_override": "paper_reading"
}
```

系统会校验论文属于当前项目且已经存在解析文本，随后返回阅读反馈、最多一个下一问题和证据页码。模型明确判断阅读目标完成后，会生成 `guided_reading_note` Artifact。

## 10. 项目与会话

```text
GET   /api/projects
GET   /api/projects/{project_id}
PATCH /api/projects/{project_id}
GET   /api/projects/{project_id}/sessions
GET   /api/sessions/{session_id}/messages
```

项目更新接口支持修改名称和结构化 `profile`。消息接口按会话内 `sequence` 正序返回。

## 11. arXiv PDF 导入与任务

```text
POST /api/papers/{paper_id}/import-pdf
POST /api/tasks/{task_id}/cancel
POST /api/tasks/{task_id}/retry
```

导入只接受论文题录中保存的 HTTP(S) PDF 地址，下载和解析均受 10 MB、前 60 页限制。失败不会删除论文题录。应用启动时遗留的 `pending` 或 `processing` 任务会被标记为 `interrupted`。

PDF 上传和 arXiv PDF 导入会先返回 `pending` 任务，解析在 FastAPI 本地后台任务中执行。前端应轮询 `GET /api/tasks/{task_id}` 获取 `processing`、`completed`、`failed` 或 `cancelled` 状态。

取消只适用于活动任务；重试只适用于 `failed`、`cancelled` 或 `interrupted` 任务，并将状态重置为 `pending`。调用方随后重新触发对应导入或解析操作。

## 12. 运行诊断

```text
GET  /api/system/settings
POST /api/system/check-storage
POST /api/system/check-ocr
POST /api/system/check-model
```

设置接口只返回非敏感运行参数，不返回 API Key。诊断接口不会回显模型输出、完整异常、论文文本或本地 `.env` 内容。
