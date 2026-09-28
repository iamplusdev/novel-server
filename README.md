# 爱小说（novel-server）

个人 **TXT 小说存储库**：服务端负责导入、刮削、管理与 API；**阅读统一用手机 Legado（开源阅读）**。

> 本项目**不做网页阅读器**。管理后台只做书库维护；正文阅读请通过 Legado 书源接入。

目标：极简、零多余依赖，可长期跑在个人服务器 / NAS 上。

## 功能

- 扫描 `novels/<书源>/<分类>/*.txt`，解析章节写入 SQLite（内容哈希未变则跳过）
- 管理后台（`/admin`）：账号登录、封面墙、书源/分类筛选、元数据编辑、刮削、体检、备份
- **两级分类**：书源（起点 / 番茄 / 纵横 / 本地）+ 站内分类，与 TXT 目录层级一致
- **刮削**：起点 / 番茄 元数据（书名、作者、简介、状态、分类、标签、封面）
- **Legado 书源**：发现页分类、搜索、详情、目录、正文（完整 URL），手机阅读主路径
- 封面本地 `covers/` 由服务直接提供

## 技术栈

| 组件 | 选型 |
|------|------|
| Web | FastAPI + Uvicorn |
| 数据库 | SQLite + SQLAlchemy 2.x |
| 管理前端 | 原生 HTML / CSS / JS（无框架） |
| 阅读端 | Legado（开源阅读）+ 本项目书源 |
| 依赖 | `fastapi` `uvicorn[standard]` `sqlalchemy` `python-multipart` |

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
  PUBLIC_BASE_URL: "http://192.168.1.100:8000"   # 改成手机能访问到的地址
```

该地址会写入 Legado 书源的 `bookSourceUrl` 与封面/章节绝对链接。

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
docker compose ps          # 等 healthcheck 变 healthy
curl -s http://127.0.0.1:8000/health
```

数据卷（务必持久化，勿打进镜像）：

| 宿主机 | 容器 | 内容 |
|--------|------|------|
| `./novels` | `/app/novels` | 源 TXT |
| `./data` | `/app/data` | SQLite、账号、备份配置 |
| `./covers` | `/app/covers` | 封面 |

### 5. 初始化

```bash
# 首次导入 TXT
docker compose exec novel-server python import_novels.py

# 管理后台创建账号（或打开网页首设）
# 浏览器：http://<host>:8000/admin
# 忘记密码时：docker compose exec novel-server python reset_auth.py admin 新密码
```

### 6. 手机 Legado 接入

1. 手机与服务器同一局域网（或已穿透），能打开 `http://<host>:8000/health`
2. 获取书源 JSON（三选一）：
   - 浏览器打开 `http://<host>:8000/legado_book_source.json`
   - 管理后台 →「API / 书源」→「下载 / 复制书源 JSON」（已填好 `PUBLIC_BASE_URL`）
   - `GET /api/legado/book-source`
3. Legado → **我的 → 书源管理 → 本地导入 / 网络导入**
4. 发现页浏览分类；搜索书名；点进详情 → 目录 → 正文

书源 JSON 根节点必须是数组 `[{...}]`，且规则含 `bookUrl`（换源需要）。

### 7. 日常操作

| 操作 | 方式 |
|------|------|
| 改元数据 / 封面 / 分类 | 管理后台书库，点封面卡片 |
| 再次导入 | 管理后台「导入」或 `docker compose exec novel-server python import_novels.py` |
| 刮削补全 | 管理后台编辑抽屉「刮削…」或体检页「一键刮削」（起点 / 番茄 / 纵横） |
| 升级 | `docker compose build && docker compose up -d`（卷数据保留） |

---

## Docker 部署说明

### compose 文件要点

```yaml
services:
  novel-server:
    build: .
    image: novel-server:latest
    container_name: novel-server
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      PUBLIC_BASE_URL: "http://192.168.1.100:8000"  # 必改
      NOVELS_DIR: "/app/novels"
      DATABASE_PATH: "/app/data/novels.db"
      COVERS_DIR: "/app/covers"
    volumes:
      - ./novels:/app/novels
      - ./data:/app/data
      - ./covers:/app/covers
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
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

- 基础镜像：`python:3.12-slim`
- 只包含运行代码与依赖；**用户数据一律 volume 挂载**
- 构建上下文通过 `.dockerignore` 排除 `data/` `covers/` `novels/` `scripts/` 等
- 导出镜像：`docker save -o novel-server-latest.tar novel-server:latest`

### 网络与安全

| 场景 | 建议 |
|------|------|
| 纯局域网 | `PUBLIC_BASE_URL=http://<内网IP>:8000`，防火墙放行 8000 |
| 外网 / 穿透 | 用 HTTPS 域名；设 `COOKIE_SECURE=1`；反代加 Basic Auth 或只允许内网 |
| Legado 外网 | 书源 `header` 可带反代账号；或走 Tailscale 等私有网 |

---

## 配置项

| 变量 | 默认 | 说明 |
|------|------|------|
| `PUBLIC_BASE_URL` | `http://127.0.0.1:8000` | **必改**，手机可访问的完整根地址（书源/封面绝对链） |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | 监听 |
| `NOVELS_DIR` | `./novels` | TXT 根目录 |
| `DATABASE_PATH` | `./data/novels.db` | SQLite 路径 |
| `COVERS_DIR` | `./covers` | 封面目录 |
| `COOKIE_SECURE` | `0` | HTTPS/反代设 `1` |
| `SCRAPER_PROXY` | （空） | 刮削代理，默认直连 |
| `SCRAPER_DELAY` | `2.0` | 批量刮削书与书基础间隔（秒），调大更不易被起点风控 |
| `SCRAPER_JITTER_MAX` | `1.5` | 在基础间隔上随机抖动上限（秒），避免固定节拍 |
| `SCRAPER_LONG_PAUSE_EVERY` | `10` | 每多少本插入一次长休息；`0` 关闭 |
| `SCRAPER_LONG_PAUSE_MIN` / `MAX` | `6` / `12` | 长休息随机秒数范围 |
| `SCRAPER_BLOCK_BREAK_AT` | `3` | 连续被拦截多少次后熔断冷却 |
| `SCRAPER_BLOCK_BREAK_SECONDS` | `180` | 熔断冷却时长（秒） |
| `SCRAPER_BROWSER_FALLBACK` | （空） | `1` 开启浏览器兜底（HTTP 失败后 Playwright/CDP 重试） |
| `CDP_URL` | `http://127.0.0.1:16002` | fnOS tieron Chrome CDP 网关（需 host 网络或可达） |
| `CDP_READY_WAIT` | `20` | 唤醒/等待 Chrome ready 超时（秒） |

### 浏览器兜底（fnOS + tieron Chrome）

批量刮削默认 HTTP；失败项会在结束后汇总，用 Playwright 连宿主 Chrome（CDP）重试：

1. `pip install -r requirements-optional.txt`（镜像内可选装）
2. `docker-compose.yml` 已用 `network_mode: host`，容器内 `127.0.0.1:16002` 即宿主机 CDP
3. 环境变量：`SCRAPER_BROWSER_FALLBACK=1`、`CDP_URL=http://127.0.0.1:16002`

日志中会看到「唤醒浏览器并兜底重试 / [浏览器] 恢复」等字样。

---

## 本地源码运行（开发）

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export PUBLIC_BASE_URL="http://192.168.1.100:8000"
python import_novels.py
python run.py
```

- 管理后台：`http://<host>:8000/admin`
- API 文档：`http://<host>:8000/docs`
- 测试：`python -m unittest tests.test_core`

---

## Legado 使用说明

**阅读入口只有 Legado**，本服务只提供 JSON API。

| Legado 功能 | 本服务 API |
|-------------|------------|
| 发现 / 分类 | `GET /api/legado/explore/{分类}?page=` |
| 搜索 | `GET /api/legado/search?q=&page=` |
| 书籍详情 | `GET /api/legado/book/{id}` |
| 目录 | `GET /api/legado/toc/{id}` |
| 正文 | `GET /api/legado/content/{book_id}/{chapter_id}` |
| 书源文件 | `GET /api/legado/book-source` 或 `/legado_book_source.json` |

公开 JSON（供调试/其它客户端）：

| 方法 | 路径 |
|------|------|
| GET | `/api/categories` |
| GET | `/api/books`（`source` `category` `q` `status` `sort` `page`） |
| GET | `/api/search?q=` |
| GET | `/api/books/{id}` |
| GET | `/api/books/{id}/chapters` |
| GET | `/api/books/{id}/chapters/{chapter_id}` |

---

## 管理后台（`/admin`）

1. 首次打开创建用户名/密码，**保存恢复码**
2. **书库**：书源行 + 分类行筛选、封面墙、点卡片编辑
3. **编辑**：书源 / 分类两级下拉、刮削、封面、删除
4. **导入**：扫描本地 `NOVELS_DIR`
5. **体检**：重复合并、损坏修复、一键刮削、按分类归位
6. **API / 书源**：查看接口、复制 Legado JSON

忘记密码：登录页「忘记密码」+ 恢复码，或容器内 `python reset_auth.py`。

---

## 目录与数据

```text
novel-server/
├── app/                 # FastAPI 应用
├── index.html admin.css admin.js admin.ui.js
├── import_novels.py     # CLI 导入
├── run.py
├── legado_book_source.json
├── Dockerfile docker-compose.yml
├── novels/              # 源 TXT（按 书源/分类 子目录）
└── covers/              # 封面
```

**books 表**：title / author / category（`起点-都市` 形式）/ intro / status / tags / cover_file / source_path / source_hash / word_count / chapter_count / latest_chapter / source / source_id / created_at / updated_at  

**chapters 表**：book_id / index / title / content

---

## 维护

- 源 TXT 内容未变时重复导入几乎无开销（SHA256 跳过）
- 升级：重新 `docker compose build && up -d`，卷数据保留
- 勿将密码、恢复码提交进仓库
- 一次性补丁脚本在 `scripts/_archive/`，日常无需执行

## License

个人使用，按需自改。
