# 研究能力训练助手

面向研究新手的论文阅读与研究能力训练工具，课程演示版。后端 FastAPI + 前端 React 18 (Vite + Ant Design 5)，主内容生成基于 OpenAI-compatible 模型网关，轻量意图分类和会话标题生成使用快速模型，文献检索走 arXiv，证据索引走 SQLite FTS5，扫描 PDF 走 Tesseract OCR 兜底。

## 系统架构

```text
浏览器前端（React 18 + Ant Design 5）
    ↓ HTTP / SSE
FastAPI 后端（Python 3.9）
    ↓
主模型（流式对话） + 快速模型（意图分类/会话标题） → 五种工作模式
    ↓
arXiv（文献检索）+ SQLite FTS5（证据检索）+ PyMuPDF（文本解析）+ Tesseract OCR
```

意图分类由 `services/intent_classifier.py` 完成：优先调用快速模型 `ROUTER_MODEL` 判别模式，失败时回退到关键词匹配，确保模型不可用也不会阻塞用户。主内容生成仍由 `QWEN_MODEL` 负责。

## 五种工作模式

| 模式 | 触发关键词 | 功能 |
|------|-----------|------|
| 普通研究问答 | 默认 | 自由研究问答，Qwen 流式回答 |
| arXiv 文献发现 | 搜索、检索、找文献、arxiv | 生成英文检索式，检索 arXiv，推荐 5–10 篇 |
| 论文引导精读 | PDF、精读、这篇文章（需指定 `paper_id`） | 苏格拉底式论文精读，自动生成阅读笔记 |
| 选题指导 | 选题、研究方向、导师建议 | 苏格拉底式逐轮追问，形成可保存的选题方案 |
| 论文框架搭建 | 帮我搭框架、章节结构、论文框架 | 苏格拉底式逐轮提问，≥95% 信心后输出最终框架方案 |

## 功能概览

- **普通研究问答**：直接提问，Qwen 流式回答
- **arXiv 文献发现**：输入研究兴趣，自动生成英文检索式、检索 arXiv、推荐 5–10 篇相关文献
- **PDF 上传与解析**：本地 PDF 上传（≤10 MB，前 60 页），文本提取 + OCR 兜底
- **arXiv PDF 导入**：对已收录的 arXiv 文献直接下载 PDF 并解析
- **证据检索**：基于 FTS5 的论文原文关键词检索，返回页码和章节信息
- **快速分析**：基于论文证据生成结构化文献卡片
- **论文对比**：在前端勾选 2–3 篇论文提交对比，自动生成结构化对比表
- **引导式精读**：苏格拉底式论文精读，支持指定 `paper_id` 进入精读模式
- **选题指导**：通过苏格拉底式追问帮助用户明确研究方向、问题和可行题目
- **论文框架搭建**：逐步澄清研究对象、核心问题、理论基础、研究方法与章节结构
- **项目自动沉淀**：首次提问自动创建项目，会话自动持久化到 SQLite
- **成果管理与导出**：文献卡片、选题卡片、框架卡片、精读笔记和对比表均可编辑、删除并导出 Markdown
- **来源回链**：成果卡片可回到来源对话或论文库中的来源论文；来源已删除时会给出提示
- **隐私保护**：本地模式（禁用远程模型）、PII 脱敏、一键清除本地数据、TTL 自动清理
- **健康检查与诊断**：前端自动轮询后端状态，OCR/存储/模型连通性诊断

## 快速启动

### 环境要求

- Python 3.9–3.12（推荐使用独立虚拟环境；不要使用 Python 3.13+）
- Node.js 18+
- Tesseract OCR（可选，未配置则普通 PDF 仍可解析）
- 阿里云百炼 API Key

### 一键启动（Windows / Linux）

项目根目录下双击 `dev-start.bat`（Windows）或运行 `./dev-start.sh`（Linux/WSL），即可在两个独立终端窗口分别启动后端（默认 8000 端口）和前端（默认 5173 端口）。

> 端口被占用时，可在命令后追加 `--port <端口号>` 或编辑脚本中的端口常量。

### 手动启动

```powershell
# 1. 安装后端依赖（项目根目录）
python -m pip install -e "backend[test]"

# 2. 复制并填写配置文件
Copy-Item backend\.env.example backend\.env
# 编辑 backend/.env，填写 DASHSCOPE_API_KEY；可选地填写 TESSERACT_EXECUTABLE

# 3. 安装前端依赖
cd frontend
npm install
cd ..

# 4. 启动后端（项目根目录）
python -m uvicorn research_agent.main:app --app-dir backend/src --host 127.0.0.1 --port 8000

# 5. 启动前端（项目根目录，另开终端）
cd frontend
npm run dev
```

访问 **http://127.0.0.1:5173** ， API 文档：http://127.0.0.1:8000/docs

## 运行测试

```powershell
# 后端（覆盖 PDF 解析、OCR、论文上传、对比、项目/会话/消息 API、模型调用日志、隐私脱敏、TTL 与数据清理）
python -m pytest backend/tests -q

# 前端（7 用例，覆盖首次项目、会话迁移、任务状态控制）
cd frontend
npm run test          # 单元测试
npm run typecheck     # TypeScript 类型检查
npm run build         # 生产构建（tsc -b && vite build）
```

## 目录结构

```text
.
├── backend/                # FastAPI 后端（Python 3.9）
│   ├── src/research_agent/
│   │   ├── api/            # API 路由（chat, papers, projects, artifacts, system, health）
│   │   ├── db/             # SQLAlchemy 模型 + SQLite 引擎
│   │   ├── repositories/   # 数据访问层
│   │   ├── schemas/        # Pydantic 请求/响应模型
│   │   ├── services/       # 业务逻辑（arxiv_search, literature, model_gateway,
│   │   │                   #   pdf_processing, paper_analysis, guided_reading,
│   │   │                   #   framework_building, topic_guidance, intent_classifier,
│   │   │                   #   arxiv_import, model_call_logging, structured_output, privacy）
│   │   ├── config.py       # 配置管理（含隐私开关）
│   │   └── main.py         # FastAPI 入口
│   └── tests/              # pytest 测试
├── frontend/               # React 前端（Vite + TypeScript + Ant Design 5）
│   └── src/
│       ├── api/            # API 客户端
│       ├── components/     # 可复用组件（ErrorBoundary, MarkdownRenderer, SearchResults, StageProgress）
│       ├── layouts/        # 布局（AppShell）
│       ├── pages/          # ChatPage, PaperReadingPage, PapersPage, ArtifactsPage, ArtifactDetailPage, SettingsPage
│       ├── store/          # Zustand 状态管理
│       ├── styles/         # 全局样式
│       ├── types/          # TypeScript 类型定义
│       └── utils/          # 工具函数 + 单元测试
├── data/                   # 应用数据（SQLite、上传文件）— 不进入版本控制
├── docs/                   # 产品使用文档
│   └── participant-user-manual.md        # 被试者产品使用手册
├── dev-start.bat           # Windows 一键启动脚本
├── dev-start.sh            # Linux / WSL 一键启动脚本
├── PROJECT_CURRENT.md      # 当前项目状态与维护边界
└── README.md               # 本文件
```

## 数据位置

- 数据库：`data/app.sqlite3`
- 上传文件：`data/uploads/`
- 应用日志：`data/logs/`（仅在使用 `dev-start.sh` 时生成）

这些内容已加入 `.gitignore`，不进入版本控制。

## OCR 配置（可选）

OCR 用于扫描型 PDF 的兜底解析。如果普通 PDF 解析得到的文本量不足 200 字符，系统会自动对缺失页面调用 Tesseract。

Windows 可安装 Tesseract OCR，并在 `backend/.env` 中填写实际安装路径。

编辑 `backend/.env`：

```dotenv
TESSERACT_EXECUTABLE=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_LANGUAGE=chi_sim+eng
```

修改后重启后端生效。可在 **系统设置 → 配置诊断 → 运行诊断** 中点击「OCR 服务」验证。

## 隐私保护

为减少把敏感信息发到远程模型的概率，后端默认提供三种隐私开关，均通过 `backend/.env` 配置（修改后需重启）：

| 变量 | 默认 | 作用 |
|------|------|------|
| `PRIVACY_PII_SCRUB` | `0` | 上传 PDF 文本提取 / OCR 之前自动替换明显邮箱、手机号、身份证号等 |
| `PRIVACY_LOCAL_ONLY` | `0` | 禁用远程模型；仅保留 arXiv 检索、PDF 解析、本地证据检索 |
| `PRIVACY_DATA_TTL_DAYS` | `0` | 启动时自动清理超过 N 天的消息与会话；`0` 表示永久保留 |

前端 **系统设置** 页提供：

- 隐私设置总览（当前是否开启本地模式 / PII 脱敏 / 数据 TTL）
- 一键「清除全部本地数据」（删除上传文件、消息、会话、项目；保留 `.env`）

所有诊断接口都不会回显模型输出、完整异常或 `.env` 内容。

## 主要接口

- `POST /api/chat/stream` — 流式对话（SSE，支持 `mode_override` 强制指定模式）
- `POST /api/chat/framework/card` — 把苏格拉底搭框架对话整理为结构化卡片 Artifact
- `POST /api/chat/topic/card` — 把选题指导对话整理为选题方案 Artifact
- `POST /api/chat/guided-reading/card` — 把论文精读对话整理为精读笔记 Artifact
- `GET /api/projects` / `GET /api/projects/{id}` / `PATCH /api/projects/{id}` — 项目
- `GET /api/projects/{id}/sessions` — 项目会话列表
- `GET /api/projects/{id}/papers` — 项目论文列表
- `GET /api/sessions/{id}/messages` — 会话消息列表
- `POST /api/papers/upload` — 上传 PDF
- `POST /api/papers/favorite` — 收藏 / 移出论文库
- `GET /api/papers/{id}/evidence?q=` — 检索原文证据
- `POST /api/papers/{id}/import-pdf` — 导入 arXiv PDF
- `POST /api/papers/{id}/quick-analysis` — 快速分析
- `POST /api/papers/compare` — 对比论文
- `GET /api/projects/{id}/artifacts` — 项目成果列表
- `GET /api/artifacts/{id}` / `PATCH /api/artifacts/{id}` / `DELETE /api/artifacts/{id}` — 成果 CRUD
- `GET /api/artifacts/{id}/markdown` — 导出 Markdown
- `GET /api/system/settings` — 运行时设置（含隐私状态）
- `POST /api/system/check-storage` / `check-ocr` / `check-model` — 诊断接口
- `POST /api/system/wipe-data` — 清除全部本地数据
- `GET /api/tasks/{id}` / `POST /api/tasks/{id}/cancel` / `POST /api/tasks/{id}/retry` — 任务状态控制

SSE 主要事件包括 `mode` / `metadata` / `stage` / `search_results` / `evidence` / `artifact` / `token` / `done` / `error`，详见 `backend/README.md` 第 4 节。

## 安全原则

- `backend/.env` 已加入 `.gitignore`，请勿将真实 API Key 提交到版本控制或聊天记录
- 默认配置不向模型发送上传 PDF 的原始文件，只发送解析/OCR 后的文本块
- `PRIVACY_PII_SCRUB=1` 启用时，会在文本进入模型前替换明显的 PII 模式
- 模型调用仅记录任务类型、耗时、是否成功等元数据，不存储完整 prompt / response

## 已知边界与注意

- 意图分类默认走 `ROUTER_MODEL` 快速模型，模型未配置 / 不可用时自动回退到关键词匹配（`OTHER` 模式）
- 引导式精读不自动猜测目标论文，必须显式传入 `paper_id`，否则返回 `PAPER_READING_REQUIRES_PAPER`
- 任务取消只对 `pending` / `processing` 状态生效；重试对 `failed` / `cancelled` / `interrupted` 生效
- 论文导入 / 上传走 FastAPI 后台任务，前端应轮询 `/api/tasks/{id}` 拿结果
- 启动时遗留的 `pending` / `processing` 任务会被自动标记为 `interrupted`，可手动重试
