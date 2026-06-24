# 后端运行说明

当前阶段已实现：

- SQLite 项目、会话、消息和模型调用日志；
- LangGraph 四模式统一路由；
- 普通研究问答；
- 阿里云百炼 Qwen 流式调用；
- arXiv 真实文献检索与项目内题录持久化；
- PDF 上传、前 60 页文本解析和 FTS5 原文证据搜索；
- Tesseract OCR 调用边界；
- SSE 聊天接口；
- 健康检查接口。

精读和诊断工作流将在后续阶段接入。当前这些模式会返回稳定的“后续阶段实现”提示，不会误调用普通问答。

## 1. 安装依赖

在项目根目录运行：

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pip install -e 'backend[test]'
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
& 'E:\anaconda927\envs\py39232\python.exe' -m uvicorn research_agent.main:app --app-dir backend/src --host 127.0.0.1 --port 8000 --reload
```

访问：

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

正确配置 Key 后，健康检查中的 `model_configured` 为 `true`。

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
- `token`：模型流式文本；
- `done`：完整回答；
- `error`：脱敏错误信息。

文献发现每次最多向 arXiv 请求 20 篇候选。系统遵守 arXiv 的请求节流要求，不并发轰炸接口；文献发现阶段只读取题录和摘要，不下载 PDF。

`search_results` 中题名、作者、摘要、日期、链接和 arXiv ID 均来自 arXiv。Qwen 只负责生成英文检索式、筛选候选和解释推荐理由。

## 5. 运行测试

测试不会调用真实模型：

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests -q
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
- 文本过少时后续可接入 OCR fallback。

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

OCR 配置通过后续设置页接入；当前服务边界已支持 Tesseract 命令构造，默认语言应使用 `chi_sim+eng`。
