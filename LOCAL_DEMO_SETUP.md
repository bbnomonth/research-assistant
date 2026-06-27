# 其它电脑本地演示部署说明

本文用于在另一台电脑上本地运行研究助手项目，适合现场演示、答辩展示或离线调试。

不要把真实 API Key、`.env`、数据库、上传论文或日志提交到 Git，也不要在截图中暴露这些内容。

## 1. 需要准备的软件

建议版本：

- Windows 10/11
- Git
- Python 3.9 到 3.12
- Node.js 18+（本项目已在 Node 24 环境下验证构建）
- Tesseract OCR，可选

本项目当前后端要求：

```text
Python >=3.9,<3.13
```

如果使用 Anaconda，建议创建一个专用环境：

```powershell
conda create -n py39232 python=3.9 -y
conda activate py39232
```

## 2. 获取代码

推荐从 GitHub 克隆：

```powershell
git clone https://github.com/bbnomonth/research-assistant.git
cd research-assistant
# 默认使用仓库当前主分支；如演示代码在其它分支，请切换到实际发布分支。
```

如果使用压缩包拷贝，请不要拷贝以下目录或文件：

```text
.env
backend/.env
data/
backend/data/
node_modules/
frontend/dist/
logs/
uploads/
*.sqlite3
```

## 3. 安装后端依赖

在项目根目录运行：

```powershell
python -m pip install -e backend[test]
```

如果不需要运行测试，可以只安装：

```powershell
python -m pip install -e backend
```

## 4. 配置后端环境变量

复制模板：

```powershell
Copy-Item backend/.env.example backend/.env
```

编辑：

```text
backend/.env
```

至少填写：

```dotenv
DASHSCOPE_API_KEY=填入你的百炼APIKey
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3.7-plus
DATABASE_PATH=data/app.sqlite3
UPLOAD_DIR=data/uploads
```

OCR 可选：

```dotenv
TESSERACT_EXECUTABLE=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_LANGUAGE=chi_sim+eng
```

隐私控制可选：

```dotenv
PRIVACY_PII_SCRUB=1
PRIVACY_LOCAL_ONLY=0
PRIVACY_DATA_TTL_DAYS=0
```

说明：

- `backend/.env` 已被 Git 忽略，不要提交。
- `DASHSCOPE_API_KEY` 只放在本机或部署平台的环境变量中。
- 如果没有 OCR，普通文本 PDF 仍可解析，扫描版 PDF 可能无法精读。

## 5. 安装前端依赖

进入前端目录：

```powershell
cd frontend
npm install
```

安装完成后回到项目根目录，或另开一个终端运行前端。

## 6. 启动后端

在项目根目录运行：

```powershell
python -m uvicorn research_agent.main:app --app-dir backend/src --host 127.0.0.1 --port 8000 --reload
```

检查后端：

```text
http://127.0.0.1:8000/api/health
```

正常结果应包含：

```json
{
  "status": "ok",
  "database": "ok",
  "model_configured": true
}
```

如果 `model_configured` 是 `false`，检查 `backend/.env` 中的 `DASHSCOPE_API_KEY`。

## 7. 启动前端

另开一个 PowerShell：

```powershell
cd frontend
npm run dev
```

打开前端提示的地址，通常是：

```text
http://127.0.0.1:5173
```

本地开发时不需要配置 `VITE_BACKEND_URL`，前端会默认调用同源或本地开发代理；如需指定后端，可在启动前设置：

```powershell
$env:VITE_BACKEND_URL="http://127.0.0.1:8000"
npm run dev
```

## 8. 演示前检查清单

1. 后端 `/api/health` 返回 `status: ok`。
2. 前端首页能打开。
3. 普通对话可以流式输出。
4. 文献检索能返回结果。
5. 收藏文献后能进入论文库。
6. 上传 PDF 后能解析。
7. 论文精读页可以打开。
8. 项目管理可以切换、编辑和删除项目。
9. 不要使用含敏感信息的真实论文做公开演示。

## 9. 常见问题

### Python 版本不兼容

如果看到类似：

```text
requires a different Python
```

请换成 Python 3.9、3.10、3.11 或 3.12。

### 前端依赖安装失败

先确认 Node.js：

```powershell
node -v
npm -v
```

建议使用 Node.js 18+。

### 后端连不上

确认后端终端没有报错，并访问：

```text
http://127.0.0.1:8000/api/health
```

### 模型不可用

确认：

```dotenv
DASHSCOPE_API_KEY=真实Key
QWEN_MODEL=百炼兼容模式支持的模型名
```

修改 `.env` 后需要重启后端。
