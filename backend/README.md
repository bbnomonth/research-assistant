# 后端运行说明

当前阶段已实现：

- SQLite 项目、会话、消息和模型调用日志；
- LangGraph 四模式统一路由；
- 普通研究问答；
- 阿里云百炼 Qwen 流式调用；
- SSE 聊天接口；
- 健康检查接口。

文献发现、PDF/OCR、证据索引、精读和诊断工作流将在后续阶段接入。当前这些模式会返回稳定的“后续阶段实现”提示，不会误调用普通问答。

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
- `token`：模型流式文本；
- `done`：完整回答；
- `error`：脱敏错误信息。

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

