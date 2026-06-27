# 当前项目说明

本文档描述当前代码库的实际产品形态和维护边界，用于替代已删除的历史开发计划和旧设计草案。

## 维护快照

- 当前主产品是本地研究工作台，不再保留独立的“研究选题诊断”入口。
- 对话意图分类和首条会话标题生成使用快速模型 `deepseek-v4-flash`，默认非思考模式。
- 论文精读、论文框架搭建、选题指导、快速分析、论文对比和成果卡片整理仍使用主模型。
- 搜索得到的文献只有被收藏或上传后才进入论文库。
- 真实配置、数据库、上传 PDF、解析结果和用户成果均不进入版本控制。

## 产品定位

研究能力训练助手是一个本地运行的研究工作台，面向研究新手，围绕“选题、检索、读文献、搭框架、沉淀成果”组织功能。

当前有效功能：

- 选题指导：苏格拉底式追问，最终可整理为选题卡片。
- 论文框架搭建：苏格拉底式追问，最终可整理为框架卡片。
- 文献检索：生成英文检索式，检索 arXiv，展示推荐文献和其它候选文献。
- 论文库：收藏或上传后的论文进入项目论文库。
- 论文精读：左侧对话、右侧 PDF 原文，基于 `paper_id` 精读指定论文。
- 快速分析：基于已解析论文原文生成中文文献解读。
- 论文对比：基于多篇已解析论文生成中文对比报告。
- 成果管理：Artifact 查看、编辑、删除和 Markdown 导出。
- 系统设置：健康检查、OCR/模型/存储诊断、本地数据清理。

不再作为独立产品入口保留的旧功能：

- 研究选题诊断
- 研究诊断报告
- 固定诊断子图

相关能力已拆分并收敛到“选题指导”和“论文框架搭建”。

## 技术结构

```text
backend/
  FastAPI + SQLAlchemy + SQLite + SSE
  services/
    conversations.py       对话编排和模式路由
    topic_guidance.py      选题指导
    framework_building.py  论文框架搭建
    literature.py          文献发现
    guided_reading.py      论文精读
    paper_analysis.py      快速分析和论文对比
    pdf_processing.py      PDF 文本解析和 OCR 兜底

frontend/
  React + Vite + TypeScript + Ant Design + Zustand
  pages/
    ChatPage.tsx           对话工作台
    PaperReadingPage.tsx   论文精读页
    PapersPage.tsx         论文库
    ArtifactsPage.tsx      成果列表
    ArtifactDetailPage.tsx 成果详情
    SettingsPage.tsx       系统设置
```

## 安全边界

- 所有清理和维护操作只应在 `E:\aaaxz\daima1022\人因工程` 内执行。
- 不提交 `backend/.env`、SQLite 数据库、上传论文、解析文本、日志和构建产物。
- 不把真实 API Key 写入文档、测试、源码或聊天记录。
- 删除文件前优先确认它们不是当前构建、测试或运行链路的一部分。
- 不使用宽泛的 `git clean -fdX`，因为它会删除 `backend/.env`、`data/`、`frontend/node_modules/` 等本地必要内容。
- 可以清理的内容仅限缓存和运行产物，例如 `__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`frontend/dist/`、后端 `_uvicorn.*.log`。

## 模型配置

主内容生成和轻量任务已经分离：

- `QWEN_MODEL`：主模型，用于论文精读、论文框架搭建、选题指导、快速分析、论文对比和成果卡片整理。
- `ROUTER_MODEL`：快速模型，默认 `deepseek-v4-flash`，用于意图分类和首条会话标题生成。
- `ROUTER_DISABLE_THINKING=1`：快速模型默认关闭思考模式。

推荐配置：

```env
DASHSCOPE_API_KEY=replace-with-your-api-key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3.7-plus

ROUTER_API_KEY=
ROUTER_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
ROUTER_MODEL=deepseek-v4-flash
ROUTER_DISABLE_THINKING=1
```

`ROUTER_API_KEY` 留空时复用 `DASHSCOPE_API_KEY`。

## 验证命令

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend\tests -q

cd frontend
npm.cmd test
npm.cmd run build
```

## 维护原则

- 新功能优先复用现有项目、会话、论文、成果模型。
- 前端状态应与后端持久化数据保持一致，避免另建隐式数据源。
- LLM 输出应有失败兜底，不允许静默伪造结果。
- 产品文案必须与当前真实功能一致，避免保留旧版诊断、旧版工作流或过时截图式说明。
