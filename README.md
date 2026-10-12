# 爱小说（novel-server）

个人 **TXT 小说存储库**：服务端负责导入、刮削、管理与 API。

**阅读路径（双端）**：
- **网页阅读器**（`/books/:id/read`）：管理后台内置，目录 / 正文 / 字号行距 / 主题 / 进度记忆
- **手机 Legado**：开源阅读 + 本项目书源（发现 / 搜索 / 目录 / 正文）

目标：极简、零多余依赖，可长期跑在个人服务器 / NAS 上。

## 功能

- 扫描 `novels/<书源>/<分类>/*.txt`，解析章节写入 SQLite（内容哈希未变则跳过）
- 管理后台：账号登录、封面墙、书源/分类筛选、元数据编辑、刮削、体检、网页阅读
- **两级分类**：书源（起点 / 番茄 / 纵横 / 本地）+ 统一分类（以起点 15 类为准），与 TXT 目录层级一致
- **刮削**：起点 / 番茄 / 纵横元数据（书名、作者、简介、状态、分类、标签、封面）
- **刮削方式**：**默认 API 直连**；`自动` = API 优先、失败用 Chrome 兜底；`Chrome` = 强制浏览器。API 侧带按域限速与 429/403/503 退避重试，降低被风控概率
- **后台任务互斥**：导入 / 体检 / 批量刮削同一时刻只允许一个运行，前端会禁用并提示
- **网页阅读器** + **Legado 书源**
- 封面本地 `covers/` 由服务直接提供；章节正文存 `data/contents/` 正文包

## 技术栈

| 组件 | 选型 |
|------|------|
| Web API | FastAPI + Uvicorn（默认 `:7312`） |
| 前端入口 | 同一 ASGI 应用：静态 + `/api` 同源（默认 `:7311`） |
| 管理前端 | Vue 3 + Vite + TypeScript + Element Plus + Pinia |
| 数据库 | SQLite + SQLAlchemy 2.x |
| 阅读端 | 网页阅读器 + Legado（开源阅读）书源 |
| 依赖 | `fastapi` `uvicorn` `sqlalchemy` `python-multipart` |

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
│   └── 奇幻/
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
   - 浏览器打开 `http://<host>:7311/legado_book_source.json`（需管理会话登录）
   - 管理后台 →「API / 书源」→「下载 / 复制书源 JSON」（已填好 `PUBLIC_BASE_URL` 与 `X-Api-Key`）
   - `GET /api/legado/book-source`
3. Legado → **我的 → 书源管理 → 本地导入 / 网络导入**
4. 发现页浏览分类；搜索书名；点进详情 → 目录 → 正文

> 公网部署：读接口（`/api/books*`、`/api/search`、`/api/legado/*`）需鉴权。请在 `.env` 设置 `READ_API_KEY`，
> 书源 JSON 会自动把该 Key 注入 `header.X-Api-Key`；未配置时读接口只认管理会话，Legado 将无法访问。

书源 JSON 根节点必须是数组 `[{...}]`，且规则含 `bookUrl`（换源需要）。

### 7. 日常操作

| 操作 | 方式 |
|------|------|
| 改元数据 / 封面 / 分类 | 管理后台书库，点封面卡片 |
| 网页阅读 | 书库/详情 →「阅读」 |
| 再次导入 | 管理后台「导入」或 `docker compose exec novel-server python import_novels.py` |
| 刮削补全 | 详情「刮削…」或体检页「一键刮削」；方式 **默认 API**，`自动`=API 优先→Chrome 兜底 |
| 体检 | 重复合并、损坏修复、按分类归位 |
| 升级 | `docker compose build && docker compose up -d`（卷数据保留） |

---

## 刮削方式（默认 API）

单本刮削弹窗与「体检 → 刮削」均可选择取数方式：

| 方式 | 说明 |
|------|------|
| **API 直连**（默认） | 只走 HTTP，轻量、速度快；不与浏览器互兜底 |
| **自动** | 唯一的两段式：先 API，失败后再用 Chrome 兜底 |
| **Chrome 浏览器** | 强制走浏览器（fnOS CDP / Playwright）；不与 API 互兜底 |

相关环境变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `SCRAPER_BROWSER_FALLBACK` | `1` | 浏览器通道开关：`1`/留空=允许；`0`=彻底禁用（`自动` 也不再兜底） |
| `CDP_URL` | `http://127.0.0.1:16002` | fnOS Chrome / CDP 网关 |
| `CDP_READY_WAIT` | `20` | 唤醒/等待 Chrome ready 超时（秒） |
| `SCRAPER_HOST_MIN_INTERVAL` | `2.0` | 同域名两次请求最小间隔（秒），较保守防封 |
| `SCRAPER_HOST_JITTER_MAX` | `0.6` | 域名间隔随机抖动上限（秒） |
| `SCRAPER_RETRY_MAX` | `3` | 收到 429/403/503 时的退避重试次数 |
| `SCRAPER_RETRY_BASE` | `2` | 退避基数（秒），指数增长，单次上限 30s |
| `SCRAPER_RESPECT_RETRY_AFTER` | `1` | 是否尊重响应的 `Retry-After` |

启用 Chrome（仅 `自动` / `Chrome` 方式需要）：

1. 安装 Playwright Python 包（`connect_over_cdp` 连宿主机 Chrome，无需 `playwright install` 内核）
   - 本机/虚机：`pip install -r requirements-optional.txt`
   - Docker：`docker compose build --build-arg INSTALL_BROWSER_DEPS=1 && docker compose up -d`
2. `docker-compose.yml` 已用 `network_mode: host`，容器内 `127.0.0.1:16002` 即宿主机 CDP
3. 缺 Playwright / CDP 时：`自动` 的 Chrome 兜底失败会返回 502 提示；默认 `API` 不受影响

**防风控**：API 请求按域名限速（默认 2s + 抖动）、命中 429/403/503 指数退避重试并（可）尊重 `Retry-After`，且复用连接会话；批量刮削另有书间间隔、长休息、单源冷却与连续被拦熔断。日志中可见「取数通道 / 浏览器兜底恢复」等字样。

> 上表中的批量节奏、限速与重试参数，均可在**管理后台 →「设置 → 刮削参数」**内调节，保存后**立即生效**（写入 `data/scraper_settings.json`）；环境变量为未保存时的默认值。

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
      READ_API_KEY: "please-change-me"              # 公网必备：Legado 读接口密钥
      TRUSTED_HOSTS: "192.168.1.100"                # 反代可信 Host（可选）
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
| 外网 / 穿透 | 用 HTTPS 域名；设 `COOKIE_SECURE=1`；**必须设 `READ_API_KEY`**（否则读接口匿名 401）；可按需设 `TRUSTED_HOSTS`；交互式文档与通配 CORS 已关闭 |
| Legado 外网 | 书源 JSON 会自动注入 `header.X-Api-Key`；或走 Tailscale 等私有网 |

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
| `COOKIE_SECURE` | `0` | HTTPS/反代设 `1`（会话 Cookie 带 Secure） |
| `READ_API_KEY` | （空） | 读接口密钥（Legado 以 `X-Api-Key` 携带）；未设则读接口只认管理会话 |
| `TRUSTED_HOSTS` | （空） | 反代可信 Host 白名单（逗号分隔）；留空则基址固定用 `PUBLIC_BASE_URL` |
| `MAX_TXT_BYTES` | `0` | 单本 TXT 导入大小上限（字节）；`0` 不限，超限跳过并计入失败 |
| `LOG_LEVEL` | `INFO` | 日志级别（`DEBUG` / `INFO` / `WARNING`） |
| `LOG_FILE` | 空 | 设为 `1` 写入 `data/novel-server.log`，或指定文件名 |
| `SCRAPER_PROXY` | （空） | 刮削代理，默认直连（不读系统代理） |
| `SCRAPER_DELAY` | `2.0` | 批量刮削书与书基础间隔（秒） |
| `SCRAPER_JITTER_MAX` | `1.5` | 基础间隔随机抖动上限（秒） |
| `SCRAPER_LONG_PAUSE_EVERY` | `5` | 每多少本插入一次长休息；`0` 关闭 |
| `SCRAPER_LONG_PAUSE_MIN` / `MAX` | `5` / `15` | 长休息随机秒数范围 |
| `SCRAPER_BLOCK_BREAK_AT` | `3` | 连续被拦截多少次后熔断冷却 |
| `SCRAPER_BLOCK_BREAK_SECONDS` | `180` | 熔断冷却时长（秒） |
| `SCRAPER_HOST_MIN_INTERVAL` | `2.0` | 同一域名两次请求最小间隔（秒）；`0` 关闭（较保守，防封） |
| `SCRAPER_HOST_JITTER_MAX` | `0.6` | 域名间隔随机抖动上限（秒） |
| `SCRAPER_RETRY_MAX` | `3` | 429/403/503 退避重试次数 |
| `SCRAPER_RETRY_BASE` | `2` | 退避基数（秒），指数增长，单次上限 30s |
| `SCRAPER_RESPECT_RETRY_AFTER` | `1` | 是否尊重响应 `Retry-After` |
| `SCRAPER_SEARCH_CACHE_TTL` | `1800` | 搜索结果缓存秒数；`0` 关闭 |
| `SCRAPER_SKIP_DETAIL` | `1` | 高置信命中跳过详情请求（省 1～3 次/本） |
| `SCRAPER_SKIP_DETAIL_SCORE` | `0.95` | 跳过详情的最低匹配分 |
| `SCRAPER_COVER` | `missing` | 封面：`missing` 已有则跳过 / `replace` 总是替换 / `skip` 从不下载 |
| `SCRAPER_SOURCE_BREAK_AT` | `2` | 单源连续被拦多少次后进入冷却 |
| `SCRAPER_SOURCE_COOLDOWN_SECONDS` | `180` | 单源冷却时长（秒），期间 `all` 跳过该源 |
| `SCRAPER_FANQIE_BING` | `1` | 批量番茄无书号时用必应反查书名 |
| `SCRAPER_FANQIE_BING_MAX` | `0` | 整批最多必应反查次数；`0` 不限 |
| `SCRAPER_BROWSER_FALLBACK` | `1` | 浏览器通道开关：`1`/留空=允许；`0`=彻底禁用（含 `自动` 兜底） |
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
# Docker 则构建时带上：docker compose build --build-arg INSTALL_BROWSER_DEPS=1

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
| OpenAPI | 生产默认关闭（`/docs`、`/redoc`、`/openapi.json` 均 404） |
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

### 公开 JSON（需读鉴权：会话 Cookie 或 `X-Api-Key`）

| 方法 | 路径 |
|------|------|
| GET | `/api/categories` |
| GET | `/api/books`（`source` `category` `q` `status` `sort` `page`） |
| GET | `/api/search?q=` |
| GET | `/api/books/{id}` |
| GET | `/api/books/{id}/chapters` |
| GET | `/api/books/{id}/chapters/{chapter_id}` |

> 上述接口与 `/api/legado/*` 均需读鉴权：网页阅读器带会话 Cookie（同源自动），
> 其它客户端带 `X-Api-Key: <READ_API_KEY>`；匿名访问返回 401。

---

## 管理后台

1. 首次打开 `http://<host>:7311/` 创建用户名/密码，**保存恢复码**
2. **书库**：书源/分类筛选、封面墙、点卡片编辑；可多选批量刮削/删除
3. **详情**：书源/分类两级下拉、刮削（默认 API）、封面、删除、进入阅读
4. **导入**：扫描本地 `NOVELS_DIR`（流式解析、编码择优），SSE 进度、可中途取消；同名同作者默认跳过
5. **体检**：重复合并、损坏修复（需显式选中）、一键刮削、按分类归位；深度体检为后台任务（带进度/停止）
6. **API / 书源**：查看接口、复制 Legado JSON
7. **设置**：主题、改密、**刮削参数**、退出、运行环境

> **任务互斥**：导入 / 体检 / 批量刮削同一时刻只允许一个运行，运行中其它入口会禁用并提示。

忘记密码：登录页「忘记密码」+ 恢复码，或容器内 `python reset_auth.py`。

---

## 目录与数据

```text
novel-server/
├── app/                 # FastAPI 应用
│   ├── routers/         # auth / admin / scrape / library / public / legado / batch_scrape
│   ├── scrapers/        # 起点 / 番茄 / 纵横 + mode + http_util + browser_fallback
│   ├── content_store.py # 章节正文包（按偏移存取）
│   ├── parsers.py       # TXT 流式解析 + 编码识别
│   ├── task_guard.py    # 长任务互斥（导入 / 体检 / 刮削）
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
- 导入：编码自动择优（UTF-8 / GBK / Big5 / UTF-16 等），异常编码会兜底解码；同名同作者默认跳过
- 正文包采用「先写临时包、DB 提交成功后再切换」，避免中断导致正文错乱
- 升级：重新 `docker compose build && up -d`，卷数据保留
- 排查问题：看容器日志；或设 `LOG_FILE=1` 落盘 `data/novel-server.log`
- 勿将密码、恢复码提交进仓库

## License

个人使用，按需自改。
