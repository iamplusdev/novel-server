# 爱小说（novel-server）

个人 **TXT 小说存储库**：服务端负责导入、刮削、管理与 API。

**阅读路径（双端）**：
- **网页阅读器**（`/books/:id/read`）：管理后台内置，目录 / 正文 / 字号行距 / 主题 / 进度记忆
- **手机 Legado**：开源阅读 + 本项目书源（发现 / 搜索 / 目录 / 正文）

目标：极简、零多余依赖，可长期跑在个人服务器 / NAS 上。

## 功能

- 扫描 `novels/<书源>/<分类>/*.txt`，解析章节写入 SQLite（内容哈希未变则跳过）
- 管理后台：账号登录、封面墙、书源/分类筛选、元数据编辑、刮削、体检、网页阅读
- **两级分类**：书源（起点 / 番茄 / 纵横 / 本地）+ 站内分类，与 TXT 目录层级一致
- **刮削**：起点 / 番茄 / 纵横元数据（书名、作者、简介、状态、分类、标签、封面）
- **刮削方式可选**：API 直连 / Chrome 浏览器（fnOS CDP）/ 自动（API 失败后切浏览器）
- **网页阅读器** + **Legado 书源**
- 封面本地 `covers/` 由服务直接提供；章节正文存 `data/contents/` 正文包

## 技术栈

| 组件 | 选型 |
|------|------|
| Web API | FastAPI + Uvicorn（默认 `:7312`） |
| 前端入口 | 静态托管 + `/api` 反代（默认 `:7311`） |
| 管理前端 | Vue 3 + Vite + TypeScript + Element Plus + Pinia |
| 数据库 | SQLite + SQLAlchemy 2.x |
| 阅读端 | 网页阅读器 + Legado（开源阅读）书源 |
| 依赖 | `fastapi` `uvicorn[standard]` `sqlalchemy` `python-multipart` |

---

## 快速开始（推荐 Docker）

### 1. 准备目录

```bash
mkdir -p novel-server && cd novel-server
# 将本仓库代码放到当前目录（或 git clone 后进入）
mkdir -p novels data covers
```

把 TXT 放到：

```text
novels/
├── 起点/
│   └── 都市/
│       └── 书名.txt
├── 番茄/
│   └── 西方奇幻/
│       └── 书名.txt
└── 玄幻/                 # 本地/未刮削也可按分类放
    └── 书名.txt
```

文件名建议：`书名.txt`、`书名(作者).txt`、`作者-书名.txt`。

### 2. 修改对外地址（必做）

编辑 `docker-compose.yml`：

```yaml
environment:
  PUBLIC_BASE_URL: "http://192.168.1.100:7311"   # 改成手机能访问到的地址
```

该地址会写入 Legado 书源的 `bookSourceUrl` 与封面/章节绝对链接。

也可复制 `.env.example` 为 `.env` 后按需修改（本地源码运行时用）。

### 3. 构建镜像

```bash
# 在仓库根目录（含 Dockerfile）
docker compose build

# 或单独构建并打标签
docker build -t novel-server:latest .

# 可选：导出镜像拷到 NAS
docker save -o novel-server-latest.tar novel-server:latest
# NAS 上：docker load -i novel-server-latest.tar
```

### 4. 启动服务

```bash
docker compose up -d
docker compose ps
curl -s http://127.0.0.1:7312/health
```

数据卷（务必持久化，勿打进镜像）：

| 宿主机 | 容器 | 内容 |
|--------|------|------|
| `./novels` | `/app/novels` | 源 TXT |
| `./data` | `/app/data` | SQLite、正文包、日志、账号 |
| `./covers` | `/app/covers` | 封面 |

### 5. 初始化

```bash
# 首次导入 TXT
docker compose exec novel-server python import_novels.py

# 浏览器打开管理后台（SPA 入口，无 /admin 后缀）
# http://<host>:7311/
# 首次进入创建账号，保存恢复码
# 忘记密码：docker compose exec novel-server python reset_auth.py admin 新密码
```

### 6. 手机 Legado 接入

1. 手机与服务器同一局域网（或已穿透），能打开 `http://<host>:7312/health`
2. 获取书源 JSON（三选一）：
   - 浏览器打开 `http://<host>:7311/legado_book_source.json`
   - 管理后台 →「API / 书源」→「下载 / 复制书源 JSON」（已填好 `PUBLIC_BASE_URL`）
   - `GET /api/legado/book-source`
3. Legado → **我的 → 书源管理 → 本地导入 / 网络导入**
4. 发现页浏览分类；搜索书名；点进详情 → 目录 → 正文

书源 JSON 根节点必须是数组 `[{...}]`，且规则含 `bookUrl`（换源需要）。

### 7. 日常操作

| 操作 | 方式 |
|------|------|
| 改元数据 / 封面 / 分类 | 管理后台书库，点封面卡片 |
| 网页阅读 | 书库/详情 →「阅读」 |
| 再次导入 | 管理后台「导入」或 `docker compose exec novel-server python import_novels.py` |
| 刮削补全 | 详情「刮削…」或体检页「一键刮削」；可选 **API / Chrome / 自动** |
| 体检 | 重复合并、损坏修复、按分类归位 |
| 升级 | `docker compose build && docker compose up -d`（卷数据保留） |

---

## 刮削方式（API / Chrome / 自动）

单本刮削弹窗与「体检 → 刮削」均可选择取数方式：

| 方式 | 说明 |
|------|------|
| **API 直连** | 轻量 HTTP 请求，速度快 |
| **Chrome 浏览器** | 经 fnOS tieron Chrome（CDP）渲染取页，抗风控更强 |
| **自动** | 优先 API，失败后自动切 Chrome（需开启浏览器兜底） |

相关环境变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `SCRAPER_BROWSER_FALLBACK` | 关 | `1` 时允许 auto 失败后走浏览器，也便于探测 CDP |
| `CDP_URL` | `http://127.0.0.1:16002` | fnOS Chrome / CDP 网关 |
| `CDP_READY_WAIT` | `20` | 唤醒/等待 Chrome ready 超时（秒） |

启用 Chrome 方式：

1. `pip install -r requirements-optional.txt`（Playwright；镜像内可选装）
2. `docker-compose.yml` 已用 `network_mode: host`，容器内 `127.0.0.1:16002` 即宿主机 CDP
3. 建议设置：`SCRAPER_BROWSER_FALLBACK=1`、`CDP_URL=http://127.0.0.1:16002`

日志中会看到「唤醒浏览器并兜底重试 / [浏览器] 恢复」等字样。

---

## Docker 部署说明

### compose 文件要点

当前仓库 `docker-compose.yml` 使用 **host 网络**（便于直达宿主机 Chrome CDP）：

```yaml
services:
  novel-server:
    build: .
    image: novel-server:latest
    container_name: novel-server
    restart: unless-stopped
    network_mode: host   # host 模式下 ports 不生效，服务监听 HOST:PORT
    environment:
      PUBLIC_BASE_URL: "http://192.168.1.100:7311"  # 必改
      HOST: "0.0.0.0"
      PORT: "7312"
      FRONTEND_PORT: "7311"
      NOVELS_DIR: "/app/novels"
      DATABASE_PATH: "/app/data/novels.db"
      COVERS_DIR: "/app/covers"
      SCRAPER_BROWSER_FALLBACK: "1"
      CDP_URL: "http://127.0.0.1:16002"
      CDP_READY_WAIT: "20"
    volumes:
      - ./novels:/app/novels
      - ./data:/app/data
      - ./covers:/app/covers
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7312/health', timeout=3)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
```

若不需要浏览器刮削、希望显式端口映射，可去掉 `network_mode: host`，改用：

```yaml
    ports:
      - "7311:7311"  # 前端入口
      - "7312:7312"  # 后端 API
```

### 常用命令

```bash
docker compose up -d              # 启动
docker compose logs -f            # 日志
docker compose exec novel-server python import_novels.py
docker compose restart
docker compose down               # 停止（保留卷数据）

# 只构建不启动
docker compose build --no-cache

# 备份宿主机数据目录即可保全书库
tar czf novel-data-$(date +%F).tar.gz data covers novels
```

### 镜像说明

- 基础镜像：`python:3.12-slim`（前端多阶段构建 `node` → 拷贝 `frontend/dist`）
- 只包含运行代码与依赖；**用户数据一律 volume 挂载**
- 构建上下文通过 `.dockerignore` 排除 `data/` `covers/` `novels/` `scripts/` 等

### 网络与安全

| 场景 | 建议 |
|------|------|
| 纯局域网 | `PUBLIC_BASE_URL=http://<内网IP>:7311`，防火墙放行 7311（前端）、7312（API） |
| 外网 / 穿透 | 用 HTTPS 域名；设 `COOKIE_SECURE=1`；反代加 Basic Auth 或只允许内网 |
| Legado 外网 | 书源 `header` 可带反代账号；或走 Tailscale 等私有网 |

---

## 配置项

| 变量 | 默认 | 说明 |
|------|------|------|
| `PUBLIC_BASE_URL` | `http://127.0.0.1:7311` | **必改**，手机可访问的完整根地址（书源/封面绝对链） |
| `HOST` / `PORT` / `FRONTEND_PORT` | `0.0.0.0` / `7312` / `7311` | 后端 API / 前端入口 |
| `NOVELS_DIR` | `./novels` | TXT 根目录 |
| `DATABASE_PATH` | `./data/novels.db` | SQLite 路径 |
| `CONTENTS_DIR` | `./data/contents` | 章节正文包目录 |
| `COVERS_DIR` | `./covers` | 封面目录 |
| `COOKIE_SECURE` | `0` | HTTPS/反代设 `1` |
| `LOG_LEVEL` | `INFO` | 日志级别（`DEBUG` / `INFO` / `WARNING`） |
| `LOG_FILE` | 空 | 设为 `1` 写入 `data/novel-server.log`，或指定文件名 |
| `SCRAPER_PROXY` | （空） | 刮削代理，默认直连（不读系统代理） |
| `SCRAPER_DELAY` | `2.0` | 批量刮削书与书基础间隔（秒） |
| `SCRAPER_JITTER_MAX` | `1.5` | 基础间隔随机抖动上限（秒） |
| `SCRAPER_LONG_PAUSE_EVERY` | `10` | 每多少本插入一次长休息；`0` 关闭 |
| `SCRAPER_LONG_PAUSE_MIN` / `MAX` | `6` / `12` | 长休息随机秒数范围 |
| `SCRAPER_BLOCK_BREAK_AT` | `3` | 连续被拦截多少次后熔断冷却 |
| `SCRAPER_BLOCK_BREAK_SECONDS` | `180` | 熔断冷却时长（秒） |
| `SCRAPER_BROWSER_FALLBACK` | 关 | `1` 开启浏览器兜底 / 可用 Chrome 方式 |
| `CDP_URL` | `http://127.0.0.1:16002` | fnOS Chrome CDP 网关 |
| `CDP_READY_WAIT` | `20` | 唤醒/等待 Chrome ready 超时（秒） |

---

## 本地源码运行（开发）

### 后端

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 可选（Chrome 刮削）：pip install -r requirements-optional.txt

export PUBLIC_BASE_URL="http://192.168.1.100:7311"   # Windows: $env:PUBLIC_BASE_URL="..."
python import_novels.py
python run.py
```

### 前端（Vite 热更新）

```bash
cd frontend
npm install
npm run dev        # 默认 :5173，代理 /api → 127.0.0.1:7312
# 生产构建（run.py 托管 frontend/dist）
npm run build
npm run typecheck
```

### 入口与测试

| 入口 | 地址 |
|------|------|
| 管理后台 | `http://<host>:7311/`（登录 `/login`） |
| 后端 API | `http://<host>:7312/` |
| OpenAPI | `http://<host>:7312/docs` |
| 健康检查 | `http://<host>:7312/health` |
| 测试 | `python -m pytest tests/ -q` 或 `python -m unittest tests.test_core` |

---

## 阅读端说明

### 网页阅读器

- 入口：书库卡片 / 详情页 →「阅读」（路由 `/books/:id/read`）
- 能力：完整目录、章节正文、字号/行距、纸白/暖黄/夜间、全屏、进度写回

### Legado

| Legado 功能 | 本服务 API |
|-------------|------------|
| 发现 / 分类 | `GET /api/legado/explore/{分类}?page=` |
| 搜索 | `GET /api/legado/search?q=&page=` |
| 书籍详情 | `GET /api/legado/book/{id}` |
| 目录 | `GET /api/legado/toc/{id}` |
| 正文 | `GET /api/legado/content/{book_id}/{chapter_id}` |
| 书源文件 | `GET /api/legado/book-source` 或 `/legado_book_source.json` |

### 公开 JSON（调试 / 其它客户端）

| 方法 | 路径 |
|------|------|
| GET | `/api/categories` |
| GET | `/api/books`（`source` `category` `q` `status` `sort` `page`） |
| GET | `/api/search?q=` |
| GET | `/api/books/{id}` |
| GET | `/api/books/{id}/chapters` |
| GET | `/api/books/{id}/chapters/{chapter_id}` |

---

## 管理后台

1. 首次打开 `http://<host>:7311/` 创建用户名/密码，**保存恢复码**
2. **书库**：书源/分类筛选、封面墙、点卡片编辑；可多选批量刮削/删除
3. **详情**：书源/分类两级下拉、刮削（可选方式）、封面、删除、进入阅读
4. **导入**：扫描本地 `NOVELS_DIR`，SSE 进度
5. **体检**：重复合并、损坏修复、一键刮削（可选方式）、按分类归位
6. **API / 书源**：查看接口、复制 Legado JSON
7. **设置**：主题、改密、退出、运行环境

忘记密码：登录页「忘记密码」+ 恢复码，或容器内 `python reset_auth.py`。

---

## 目录与数据

```text
novel-server/
├── app/                 # FastAPI 应用
│   ├── routers/         # auth / admin / scrape / library / public / legado
│   ├── scrapers/        # 起点 / 番茄 / 纵横 + mode + browser_fallback
│   └── ...
├── frontend/            # Vue3 + Vite（构建产物 frontend/dist）
├── tests/               # pytest / unittest
├── import_novels.py     # CLI 导入
├── run.py               # 同时拉起前端入口 + 后端 API
├── legado_book_source.json
├── Dockerfile  docker-compose.yml  .env.example
├── novels/              # 源 TXT（书源/分类 子目录）
├── covers/              # 封面
└── data/                # novels.db、contents/、日志（volume）
```

**books 表**：title / author / category（`起点-都市` 形式）/ intro / status / tags / cover_file / source_path / source_hash / word_count / chapter_count / latest_chapter / source / source_id / read_percent / read_chapter_index / read_at / created_at / updated_at

**chapters 表**：book_id / index / title / content_offset / content_length / content_chars（正文在 `data/contents/{book_id}.bin`，遗留 `content` 列仅作兼容）

---

## 维护

- 源 TXT 内容未变时重复导入几乎无开销（SHA256 跳过）
- 升级：重新 `docker compose build && up -d`，卷数据保留
- 排查问题：看容器日志；或设 `LOG_FILE=1` 落盘 `data/novel-server.log`
- 勿将密码、恢复码提交进仓库

## License

个人使用，按需自改。
