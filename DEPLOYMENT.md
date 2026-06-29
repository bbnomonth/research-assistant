# 环境部署说明

本文档只说明本地部署和其它电脑演示部署。不要把真实 API Key、`backend/.env`、数据库、上传论文或日志提交到 Git。

## 1. 环境要求

- Windows 10/11 或 Linux/WSL。
- Python：`>=3.9,<3.13`，推荐 3.9、3.10 或 3.11；不要使用 Python 3.13+。
- Node.js：18+，本项目已在 Node 24 环境下验证构建。
- Tesseract OCR：可选。普通文本 PDF 不依赖 OCR，扫描版 PDF 建议安装并配置。
- 模型 API Key：需要百炼兼容 OpenAI API 的 Key，写入 `backend/.env`。

## 2. 获取代码

如果从 Git 获取代码：

```powershell
git clone https://github.com/bbnomonth/research-assistant.git
cd research-assistant
```

如果用 U 盘或压缩包拷贝到其它电脑，建议只拷贝源码和文档，不拷贝以下本地数据：

```text
backend/.env
data/
exports/
frontend/node_modules/
frontend/dist/
*.sqlite3
*.log
```

## 3. 配置后端

在项目根目录复制环境变量模板：

```powershell
Copy-Item backend\.env.example backend\.env
```

编辑 `backend/.env`，至少填写：

```dotenv
DASHSCOPE_API_KEY=填入你的百炼APIKey
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3.7-plus

ROUTER_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
ROUTER_MODEL=deepseek-v4-flash
ROUTER_DISABLE_THINKING=1

DATABASE_PATH=data/app.sqlite3
UPLOAD_DIR=data/uploads
```

如果安装了 Tesseract OCR，继续填写：

```dotenv
TESSERACT_EXECUTABLE=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_LANGUAGE=chi_sim+eng
```

隐私相关配置可选：

```dotenv
PRIVACY_PII_SCRUB=1
PRIVACY_LOCAL_ONLY=0
PRIVACY_DATA_TTL_DAYS=0
```

## 4. 安装依赖

后端依赖：

```powershell
python -m pip install -e "backend[test]"
```

如果已经激活了目标 Python 环境，也可以写成：

```powershell
python -m pip install -e "backend[test]"
```

前端依赖：

```powershell
cd frontend
npm install
cd ..
```

## 5. 启动项目

方式一：Windows 一键启动。

如果你已经激活了 Python 环境，直接运行：

```powershell
.\dev-start.bat
```

如果需要指定 Python 路径，先设置 `PYTHON_EXE`：

```powershell
$env:PYTHON_EXE="<你的 Python 路径>\python.exe"
.\dev-start.bat
```

方式二：手动启动。

终端 1 启动后端：

```powershell
python -m uvicorn research_agent.main:app --app-dir backend/src --host 127.0.0.1 --port 8000
```

终端 2 启动前端：

```powershell
cd frontend
npm run dev
```

访问地址：

- 前端：`http://127.0.0.1:5173`
- 后端健康检查：`http://127.0.0.1:8000/api/health`
- 后端接口文档：`http://127.0.0.1:8000/docs`

## 6. 本地验证

前端构建：

```powershell
cd frontend
npm run build
cd ..
```

后端测试：

```powershell
python -m pytest backend\tests -q --basetemp data\pytest-run-workflow
```

测试完成后可以删除 `data\pytest-run-workflow`。不要删除 `data\app.sqlite3` 和 `data\uploads`，它们是运行数据。

## 7. 演示前检查清单

1. `http://127.0.0.1:8000/api/health` 返回 `status: ok`。
2. 前端页面可以打开。
3. 普通对话可以流式输出。
4. 文献检索能返回候选论文。
5. 收藏文献后能进入论文库。
6. PDF 上传或导入后能打开 `/api/papers/{paper_id}/pdf`。
7. 论文精读页能左侧对话、右侧显示论文。
8. 项目成果卡片可以查看、编辑、删除和导出。
9. 不在公开演示中使用含敏感信息的真实论文或真实个人数据。

## 8. 常见问题

### Python 版本不兼容

如果安装依赖时报 `requires a different Python`，切换到 Python 3.9、3.10、3.11 或 3.12。

### 前端依赖安装失败

先确认 Node.js 和 npm：

```powershell
node -v
npm -v
```

建议使用 Node.js 18+。

### 后端启动后模型不可用

检查 `backend/.env`：

```dotenv
DASHSCOPE_API_KEY=replace-with-your-api-key
QWEN_MODEL=百炼兼容模式支持的模型名
```

修改 `.env` 后必须重启后端。

### PDF 若精读没有原文

确认对应论文已经上传或导入 PDF，并检查：

```text
data/uploads/
http://127.0.0.1:8000/api/papers/{paper_id}/pdf
```

扫描版 PDF 需要配置 Tesseract OCR 才能获得更完整的文本。
