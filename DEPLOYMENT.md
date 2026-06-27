# 云部署说明

本项目建议采用前后端分离部署：

- Netlify：部署 `frontend` 静态前端。
- Python 后端平台：部署 `backend` FastAPI 服务，例如 Render、Railway、Fly.io、VPS 或云服务器。
- 持久化磁盘或云存储：保存 SQLite 数据库、上传 PDF 和解析结果。

不要把真实 API Key、`.env`、数据库、上传论文或日志提交到 Git。

## 1. 部署前检查

在本地确认构建和测试通过：

```powershell
cd frontend
npm run build
```

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests -q
```

当前 Git 分支需要先推送到 GitHub，或者合并到 Netlify 绑定的生产分支。

## 2. Netlify 前端配置

仓库根目录已经提供 `netlify.toml`：

```toml
[build]
  base = "frontend"
  command = "npm run build"
  publish = "dist"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

在 Netlify 中连接 GitHub 仓库后，构建配置会自动读取该文件。

Netlify 环境变量：

```text
VITE_BACKEND_URL=https://your-backend-domain.example.com
```

`VITE_BACKEND_URL` 是构建时变量，修改后必须重新部署前端。

## 3. 后端部署配置

后端启动命令：

```bash
uvicorn research_agent.main:app --app-dir backend/src --host 0.0.0.0 --port $PORT
```

如果平台不提供 `$PORT`，使用平台指定端口，例如 `8000`。

安装命令：

```bash
python -m pip install -e backend
```

后端环境变量：

```text
DASHSCOPE_API_KEY=replace-in-platform-secret-settings
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3.7-plus
DATABASE_PATH=/persistent/data/app.sqlite3
UPLOAD_DIR=/persistent/data/uploads
CORS_ALLOWED_ORIGINS=https://your-site.netlify.app,https://your-custom-domain.example.com
```

OCR 可选环境变量：

```text
TESSERACT_EXECUTABLE=/usr/bin/tesseract
OCR_LANGUAGE=chi_sim+eng
```

隐私控制可选环境变量：

```text
PRIVACY_PII_SCRUB=1
PRIVACY_LOCAL_ONLY=0
PRIVACY_DATA_TTL_DAYS=0
```

说明：

- `DASHSCOPE_API_KEY` 只在后端平台的 Secret/Environment Variables 中配置。
- `CORS_ALLOWED_ORIGINS` 必须包含 Netlify 分配的域名和你的自定义域名。
- `DATABASE_PATH` 和 `UPLOAD_DIR` 必须指向持久化磁盘，否则重新部署后数据会丢失。
- 如果后端平台没有安装 Tesseract，扫描版 PDF 的 OCR 可能不可用，但普通文本 PDF 仍可解析。

## 4. 上线验证

部署后依次检查：

1. 打开 Netlify 首页。
2. 刷新任意前端子页面，确认没有 404。
3. 访问 `https://your-backend-domain.example.com/api/health`。
4. 在浏览器开发者工具中确认没有 CORS 报错。
5. 测试普通对话的流式输出。
6. 测试文献检索。
7. 测试 PDF 上传、解析和论文精读页。
8. 确认后端平台的持久化目录中生成数据库和上传文件。

## 5. 需要人工操作的部分

你需要在平台后台完成：

1. GitHub：推送当前分支，或合并到生产分支。
2. Netlify：连接 GitHub 仓库并创建站点。
3. Netlify：设置 `VITE_BACKEND_URL`。
4. 后端平台：创建 Python Web Service。
5. 后端平台：配置 Secret 环境变量，尤其是 `DASHSCOPE_API_KEY`。
6. 后端平台：配置持久化磁盘，并把 `DATABASE_PATH`、`UPLOAD_DIR` 指向该磁盘。
7. 后端平台：把实际 Netlify 域名填入 `CORS_ALLOWED_ORIGINS`。

