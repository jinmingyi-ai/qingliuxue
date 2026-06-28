# 轻留学部署说明

## 本地开发

1. 安装依赖：

```bash
python -m pip install -r requirements.txt
```

2. 启动后端：

```bash
set JWT_SECRET=replace-with-a-long-random-secret
python -m uvicorn app.backend.api.main:app --host 127.0.0.1 --port 8000
```

3. 启动前端：

```bash
set API_BASE_URL=http://127.0.0.1:8000
python -m streamlit run app/frontend/streamlit_app.py --server.port 8501
```

访问 `http://127.0.0.1:8501/?page=home`。

## Docker 本地运行

```bash
docker compose up --build
```

前端：`http://127.0.0.1:8501`

后端健康检查：`http://127.0.0.1:8000/health`

## GitHub + Railway

1. 新建 GitHub 仓库，把本项目推送上去。
2. Railway 里选择 `New Project -> Deploy from GitHub repo`。
3. Railway 会读取 `Dockerfile` 和 `railway.json`，一个容器里同时启动 FastAPI 与 Streamlit。
4. 设置环境变量：
   - `JWT_SECRET`: 一段足够长的随机字符串
   - `API_BASE_URL`: `http://127.0.0.1:8000`
   - `DATABASE_URL`: `sqlite:////app/app/data/auth/qingliuxue.db`
5. Railway 对外暴露 Streamlit 端口，FastAPI 只在容器内给前端调用。

当前 demo 使用 SQLite 和本地 JSON 记忆文件，适合展示项目。若要正式多人长期使用，建议升级为 PostgreSQL，并把记忆、会话、问卷和检索日志迁移到数据库。

