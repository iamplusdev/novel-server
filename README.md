# 爱小说（novel-server）

个人 **TXT 小说库**：导入、刮削、体检、网页阅读，并通过 Legado（开源阅读）书源在手机上阅读。
目标是依赖少、部署简单，可长期跑在个人服务器 / NAS 上。

- **源码仓库（唯一）**：<https://github.com/iamplusdev/novel-server>

## 目录

- [功能一览](#功能一览)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [Legado 接入](#legado-接入)
- [WebDAV 进度同步](#webdav-进度同步)
- [管理后台](#管理后台)
- [配置](#配置)
- [API](#api)
- [目录与数据](#目录与数据)
- [开发与测试](#开发与测试)
  - [发布流程](#发布流程)
- [维护与备份](#维护与备份)
- [安全建议](#安全建议)
- [常见问题](#常见问题)
- [License](#license)

## 功能一览

| 模块 | 能力 |
|------|------|
| 书库 | 封面墙、书源/分类筛选、搜索高亮、排序、分页；筛选状态写入 URL；「继续阅读」入口 |
| 批量操作 | 多选批量编辑分类/标签/状态、批量刮削、批量删除 |
| 导入 | 扫描 `novels/`，流式解析、编码自动择优、内容哈希去重、SSE 进度、可取消；失败项可单本/批量重试 |
| 分类 | 两级分类：书源（起点/番茄/纵横/本地）+ 起点 15 类标准分类 |
| 刮削 | 起点 / 番茄 / 纵横；默认 API 直连，可选 Chrome 兜底；按域限速与退避重试；批量结果可筛选/导出 CSV |
| 网页阅读器 | 目录筛选与定位、书内搜索精确跳转、上下滚动/左右翻页、字体字号行距、内容宽度、三种主题、沉浸顶栏、章内位置记忆、下一章预取 |
| Legado | 发现 / 搜索 / 详情 / 目录 / 正文 / 书源 JSON |
| 进度同步 | 与 Legado 共用 WebDAV `bookProgress`：打开拉取、关闭推送、详情页手动诊断 |
| 体检 | 重复合并、异常类型筛选、修复前只读预览、损坏修复、按分类归位；深度体检后台执行、带进度 |
| 封面 | 本地上传 / 刮削下载；可选 Pillow 生成 webp 缩略图，支持批量回填 |
| 阅读统计 | 已读/在读/读完/未读、估算已读字数、平均进度、最近阅读、已读分类分布 |
| 自动化 | 可配置间隔的自动体检；导入/刮削进行中自动跳过 |
| 其他 | 单账号登录 + 恢复码、长任务互斥、可选 API Key 读鉴权 |

**阅读路径**：

- 网页阅读器：`/books/:id/read`
- 手机：Legado + 本项目书源

## 技术栈

| 组件 | 选型 |
|------|------|
| Web API | FastAPI + Uvicorn（默认 `:7312`） |
| 前端 | Vue 3 + Vite + TypeScript + Element Plus（样式按需加载）+ Pinia |
| 前端入口 | 同一 ASGI 应用：静态 + `/api` 同源（默认 `:7311`） |
| 数据库 | SQLite + SQLAlchemy 2.x（WAL） |
| 正文存储 | `data/contents/{book_id}.bin` 正文包，按字节偏移读取 |
| 统计缓存 | 进程内短 TTL 缓存，默认 30 秒，可用 `STATS_CACHE_TTL` 调整 |
| 必装依赖 | `fastapi` `uvicorn` `sqlalchemy` `python-multipart` |
| 可选依赖 | `playwright`（Chrome 刮削）、`Pillow`（封面缩略图） |

要求 Python **3.10+**（Docker 镜像使用 3.12）。

---

## 快速开始

### 方式一：Docker（推荐）

#### 1. 准备目录与 TXT

```bash
mkdir -p novel-server && cd novel-server
git clone https://github.com/iamplusdev/novel-server.git .
mkdir -p novels data covers
```

导入器只扫描以下位置：

```text
novels/
├── 起点/都市/书名.txt       # 书源（起点 / 番茄 / 纵横）+ 分类
├── 番茄/奇幻/书名.txt
├── 纵横/仙侠/书名.txt
└── 未分类/书名.txt          # 递归扫描该目录
```

- 分类需为起点 15 类之一，未知分类归入「未分类」。
- `novels/` 根目录散落的 txt、其他目录不会导入。
- 文件名建议：`书名.txt`、`书名(作者).txt`、`作者-书名.txt`。

#### 2. 必改配置

完整示例见仓库 `docker-compose.yml`，最关键的两项：

```yaml
environment:
  PUBLIC_BASE_URL: "https://novel.example.com"   # 或 http://192.168.1.100:7311
  READ_API_KEY: "please-change-me"               # 公网/Legado 必填
```

- `PUBLIC_BASE_URL` 决定书源里的 `bookSourceUrl`、封面与章节绝对链接。
- 也可设 `TRUSTED_HOSTS=novel.example.com`，命中白名单时按请求 Host 推导基址（反代需透传 `Host` / `X-Forwarded-*`）。
- `docker-compose.yml` 的 `environment:` 会**覆盖** `.env`；改了 `.env` 不生效时先检查 compose。
- 改完地址后需 `docker compose up -d` 重建，并在 Legado 中**删除旧书源重新导入**。

#### 3. 构建与启动

```bash
# 方式 A：本地构建
docker compose build
docker compose up -d

# 方式 B：使用预构建镜像
docker pull iamplusdev/novel-server:latest
# 将 compose 中的 build: 段删除，改为 image: iamplusdev/novel-server:latest
docker compose up -d

docker compose ps
curl -s http://127.0.0.1:7312/health
```

数据卷（务必持久化）：

| 宿主机 | 容器 | 内容 |
|--------|------|------|
| `./novels` | `/app/novels` | 源 TXT |
| `./data` | `/app/data` | SQLite、正文包、账号、配置、日志 |
| `./covers` | `/app/covers` | 封面（含派生缩略图） |

#### 4. 初始化

```bash
# 首次导入
docker compose exec novel-server python import_novels.py

# 打开管理后台（SPA 入口，无 /admin 后缀）
# http://<host>:7311/
# 首次进入创建账号并保存恢复码
# 忘记密码：docker compose exec novel-server python reset_auth.py admin 新密码
```

### 方式二：本地源码

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 可选：Chrome 刮削 + 封面缩略图
# pip install -r requirements-optional.txt

export PUBLIC_BASE_URL="http://192.168.1.100:7311"
python import_novels.py
python run.py
```

前端开发模式：

```bash
cd frontend
npm install
npm run dev        # :5173，代理 /api → 127.0.0.1:7312
npm run build      # 生产构建到 frontend/dist，由 run.py 托管
```

### 入口

| 入口 | 地址 |
|------|------|
| 管理后台 | `http://<host>:7311/`（登录 `/login`） |
| 后端 API | `http://<host>:7312/` |
| 健康检查 | `http://<host>:7312/health` |
| OpenAPI | 生产默认关闭（`/docs`、`/redoc`、`/openapi.json` 均 404） |

---

## Legado 接入

1. 手机与服务器同一局域网（或已穿透），能打开 `http://<域名或IP>:7312/health`。
2. 获取书源 JSON（三选一）：
   - 浏览器打开 `http://<域名或IP>:7311/legado_book_source.json`（需管理会话登录）
   - 管理后台 →「API / 书源」→「下载 / 复制书源 JSON」
   - `GET /api/legado/book-source`
3. Legado → **我的 → 书源管理 → 本地导入 / 网络导入**。
4. 发现页浏览分类；搜索书名；进入详情 → 目录 → 正文。

> 公网部署必须设置 `READ_API_KEY`。书源 JSON 会自动注入 `header.X-Api-Key`；
> 未配置时读接口只认管理会话，Legado 将无法访问。

书源 JSON 根节点必须是数组 `[{...}]`，且规则含 `bookUrl`（换源需要）。

| Legado 功能 | 本服务 API |
|-------------|------------|
| 发现 / 分类 | `GET /api/legado/explore/{分类}?page=` |
| 搜索 | `GET /api/legado/search?q=&page=` |
| 书籍详情 | `GET /api/legado/book/{id}` |
| 目录 | `GET /api/legado/toc/{id}` |
| 正文 | `GET /api/legado/content/{book_id}/{chapter_id}` |
| 书源文件 | `GET /api/legado/book-source` 或 `/legado_book_source.json` |

---

## WebDAV 进度同步

与 Legado 共用同一个 WebDAV 的 `bookProgress/书名_作者.json`，实现跨端进度同步。
配置入口：**设置 → WebDAV 进度同步**。

| 字段 | 说明 |
|------|------|
| WebDAV 地址 | 如 `https://dav.jianguoyun.com/dav/` |
| 账号 / 密码 | WebDAV 账号与应用密码；密码只写不读 |
| 目录 | Legado 的 WebDAV 目录，默认 `legado`；Legado 未勾选「创建 Legado 文件夹」时留空 |
| 校验证书 | 自签名 NAS 证书可关闭校验 |
| 超时 | 单次 WebDAV 请求超时（2–20 秒） |

**同步行为**

- **打开阅读页**：拉取远端进度，按 `durChapterTime` 最新者优先；章节标题优先匹配、序号兜底，然后定位到对应章节。
- **关闭 / 切后台**：`pagehide` / `visibilitychange` 时推送当前章节与估算的章内位置。
- **防覆盖**：推送前先读远端，若另一台设备刚写入更新进度则跳过本次写入。
- **详情页诊断**：书籍详情 →「进度同步」可查看本地/远端进度、实际远程文件名、章节匹配结果，并手动拉取或推送。
- **Legado 侧**：需在「备份与恢复」中开启「同步阅读进度」，并填写同一个 WebDAV 地址、账号与目录。

**限制**

- Legado 只在 App 启动或打开书籍时下载进度，无法实时接收推送。
- 文件名由「书名_作者」决定，两端书名、作者必须完全一致。
- 拉取按章节标题优先纠正；推送使用本地章节序号。若 Legado 通过本服务书源阅读同一本书，章节顺序一致可直接对应。
- 章内位置为滚动/翻页进度换算的估算值，章节定位准确。
- 密码以 0600 权限明文保存在 `data/webdav_settings.json`（接口不回传），请保护数据目录并优先使用 HTTPS。

> WebDAV 使用 Basic Auth，公网访问请使用 HTTPS。

---

## 管理后台

1. **首次使用**：打开 `http://<host>:7311/` 创建账号，保存恢复码。
2. **书库**：书源/分类筛选、搜索高亮、封面墙、排序、分页；筛选状态写入 URL（刷新/返回可恢复）；顶部「继续阅读」；书卡显示进度、字数、章节、更新时间和书源。
3. **详情**：编辑书名/作者/分类/状态/标签/简介、上传或刮削封面、进入阅读、WebDAV 进度诊断。
4. **导入**：扫描 `NOVELS_DIR`，SSE 进度，可中途取消；同名同作者默认跳过；失败文件可单本或批量重试。
5. **体检**：重复合并、异常类型筛选、修复前只读预览、损坏修复（需显式选择）、一键刮削、按分类归位；深度体检在后台执行。
6. **统计**：已读/在读/读完/未读、估算已读字数、平均进度、最近阅读和分类分布。
7. **API / 书源**：查看接口、复制 Legado JSON。
8. **设置**：主题、改密、刮削参数、自动体检、WebDAV 进度同步、运行环境。

> **任务互斥**：导入 / 体检 / 批量刮削同一时刻只允许一个运行，其它入口会禁用并提示。

忘记密码：登录页「忘记密码」+ 恢复码，或容器内执行 `python reset_auth.py`。

---

## 配置

### 基础配置

| 变量 | 默认 | 说明 |
|------|------|------|
| `PUBLIC_BASE_URL` | `http://127.0.0.1:7311` | **必改**，手机可访问的完整根地址 |
| `HOST` / `PORT` / `FRONTEND_PORT` | `0.0.0.0` / `7312` / `7311` | 后端 API / 前端入口 |
| `NOVELS_DIR` | `./novels` | TXT 根目录 |
| `DATABASE_PATH` | `./data/novels.db` | SQLite 路径 |
| `CONTENTS_DIR` | `./data/contents` | 章节正文包目录 |
| `COVERS_DIR` | `./covers` | 封面目录 |
| `COOKIE_SECURE` | `0` | HTTPS/反代设 `1` |
| `READ_API_KEY` | （空） | 读接口密钥（`X-Api-Key`）；未设则只认管理会话 |
| `TRUSTED_HOSTS` | （空） | 反代可信 Host 白名单（逗号分隔） |
| `MAX_TXT_BYTES` | `0` | 单本 TXT 大小上限（字节）；`0` 不限 |
| `STATS_CACHE_TTL` | `30` | 统计接口缓存秒数；`0` 关闭 |
| `MAINTENANCE_SCHEDULER` | `1` | 是否启动自动体检调度器；`0` 关闭 |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` |
| `LOG_FILE` | 空 | `1` 写入 `data/novel-server.log`，或指定文件名 |

### 自动体检

在 **设置 → 自动体检** 中启用并设置间隔（1–720 小时）、是否深度体检。配置保存在
`data/maintenance_settings.json`，调度器随应用启动，每 60 秒检查一次。

- 只执行书库体检（重复 / 异常），不会自动导入源 TXT。
- 导入或刮削正在运行时跳过，下个周期重试。
- 当前按单进程部署设计；多 uvicorn worker 会各自运行调度器。
- 最近触发时间和启动错误会显示在设置页。

### 刮削

单本刮削与批量刮削均可选择取数方式：

| 方式 | 说明 |
|------|------|
| **API 直连**（默认） | 只走 HTTP，速度快，不与浏览器互兜底 |
| **自动** | 先 API，失败后再用 Chrome 兜底 |
| **Chrome 浏览器** | 强制走浏览器（fnOS CDP / Playwright） |

启用 Chrome（仅 `自动` / `Chrome` 需要）：

1. 安装 Playwright：`pip install -r requirements-optional.txt`
   - Docker：`docker compose build --build-arg INSTALL_BROWSER_DEPS=1 && docker compose up -d`
2. `docker-compose.yml` 使用 `network_mode: host`，容器内 `127.0.0.1:16002` 即宿主机 CDP。
3. 缺 Playwright / CDP 时，`自动` 的兜底会返回 502；默认 `API` 不受影响。

`requirements-optional.txt` 同时包含可选的 **Pillow**：安装后书库列表按需生成 webp 缩略图；
未安装时 `/thumbs` 自动回退原封面，不影响其它功能。

以下参数可在**设置 → 刮削参数**中调整，保存后立即生效（写入 `data/scraper_settings.json`）；
环境变量仅作为未保存时的默认值。

| 变量 | 默认 | 说明 |
|------|------|------|
| `SCRAPER_PROXY` | （空） | 刮削代理，默认直连 |
| `SCRAPER_DELAY` | `2.0` | 批量刮削书与书基础间隔（秒） |
| `SCRAPER_JITTER_MAX` | `1.5` | 基础间隔随机抖动上限（秒） |
| `SCRAPER_LONG_PAUSE_EVERY` | `5` | 每多少本插入长休息；`0` 关闭 |
| `SCRAPER_LONG_PAUSE_MIN` / `MAX` | `5` / `15` | 长休息随机秒数范围 |
| `SCRAPER_BLOCK_BREAK_AT` | `3` | 连续被拦截多少次后熔断 |
| `SCRAPER_BLOCK_BREAK_SECONDS` | `180` | 熔断冷却时长（秒） |
| `SCRAPER_HOST_MIN_INTERVAL` | `2.0` | 同域名请求最小间隔（秒） |
| `SCRAPER_HOST_JITTER_MAX` | `0.6` | 域名间隔随机抖动上限（秒） |
| `SCRAPER_RETRY_MAX` | `3` | 429/403/503 退避重试次数 |
| `SCRAPER_RETRY_BASE` | `2` | 退避基数（秒），指数增长，单次上限 30s |
| `SCRAPER_RESPECT_RETRY_AFTER` | `1` | 是否尊重响应 `Retry-After` |
| `SCRAPER_SEARCH_CACHE_TTL` | `1800` | 搜索结果缓存秒数；`0` 关闭 |
| `SCRAPER_SKIP_DETAIL` | `1` | 高置信命中跳过详情请求 |
| `SCRAPER_SKIP_DETAIL_SCORE` | `0.95` | 跳过详情的最低匹配分 |
| `SCRAPER_COVER` | `missing` | `missing` / `replace` / `skip` |
| `SCRAPER_SOURCE_BREAK_AT` | `2` | 单源连续被拦多少次后冷却 |
| `SCRAPER_SOURCE_COOLDOWN_SECONDS` | `180` | 单源冷却时长（秒） |
| `SCRAPER_FANQIE_BING` | `1` | 番茄无书号时用必应反查书名 |
| `SCRAPER_FANQIE_BING_MAX` | `0` | 整批最多必应反查次数；`0` 不限 |
| `SCRAPER_BROWSER_FALLBACK` | `1` | 浏览器通道开关；`0` 彻底禁用 |
| `CDP_URL` | `http://127.0.0.1:16002` | fnOS Chrome / CDP 网关 |
| `CDP_READY_WAIT` | `20` | 唤醒/等待 Chrome ready 超时（秒） |

### 反向代理

- host 网络下服务直接监听 `HOST:PORT`（默认 7311 前端、7312 API）。
- 反代请透传 `Host` 与 `X-Forwarded-Proto`；HTTPS 下设 `COOKIE_SECURE=1`。
- 交互式文档与通配 CORS 默认关闭。

---

## API

公开读接口需要读鉴权：网页阅读器使用会话 Cookie，其它客户端带 `X-Api-Key: <READ_API_KEY>`。
列表接口支持 `fields=id,name,author,cover_thumb_url` 裁剪返回字段；`id` 始终保留，未知字段忽略。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/categories` | 分类及数量 |
| GET | `/api/tags` | 标签云 |
| GET | `/api/books` | 列表；`source` `category` `q` `status` `tag` `sort` `page` `fields` |
| GET | `/api/search?q=` | 搜索；支持 `fields` 字段裁剪 |
| GET | `/api/books/{id}` | 详情 |
| GET | `/api/books/{id}/chapters` | 目录（分页） |
| GET | `/api/books/{id}/chapters/{chapter_id}` | 正文 |

管理端（需管理员会话）常用接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/PATCH | `/api/admin/books`、`/api/admin/books/{id}` | 列表 / 编辑；列表支持 `fields` |
| GET | `/api/admin/stats/reading` | 阅读统计概览 |
| POST | `/api/admin/books/batch/update` | 批量编辑分类/标签/状态 |
| POST | `/api/admin/import`、`/api/admin/import/cancel` | 导入 |
| POST | `/api/admin/import/retry` | 仅重试失败文件 |
| GET | `/api/admin/import/stream` | 导入进度 SSE |
| GET/POST | `/api/admin/library/report`、`/scan` | 体检 |
| POST | `/api/admin/library/repair/preview` | 修复前只读预览 |
| POST | `/api/admin/scrape/search`、`/books/{id}/apply` | 单本刮削 |
| POST | `/api/admin/scrape/batch/start` | 批量刮削 |
| GET | `/api/admin/scrape/batch/stream` | 批量刮削进度 SSE |
| POST | `/api/admin/books/thumbs/rebuild` | 批量回填封面缩略图 |
| GET/PUT | `/api/admin/settings/maintenance` | 自动体检配置 |
| GET/PUT | `/api/admin/settings/webdav` | WebDAV 配置 |
| POST | `/api/admin/settings/webdav/test` | 测试连接 |
| GET | `/api/admin/books/{id}/sync/info` | 进度诊断 |
| POST | `/api/admin/books/{id}/sync/pull` | 拉取远端进度 |
| POST | `/api/admin/books/{id}/sync/push` | 后台推送进度 |
| POST | `/api/admin/books/{id}/sync/push-now` | 手动推送进度 |

---

## 目录与数据

```text
novel-server/
├── app/
│   ├── routers/             # auth / admin / public / legado / scrape / library / batch_scrape / sync
│   ├── scrapers/            # 起点 / 番茄 / 纵横 + 限速重试 + 浏览器兜底
│   ├── content_store.py     # 正文包（按偏移存取）
│   ├── parsers.py           # TXT 解析 + 编码识别
│   ├── sync_progress.py     # Legado 进度同步
│   ├── maintenance.py       # 自动体检调度器
│   ├── maintenance_settings.py
│   ├── stats_cache.py       # 统计接口短 TTL 缓存
│   ├── webdav.py            # 标准库 WebDAV 客户端
│   ├── webdav_settings.py   # WebDAV 配置
│   ├── scraper_settings.py  # 刮削参数运行时配置
│   └── task_guard.py        # 长任务互斥
├── frontend/                # Vue3 + Vite
├── tests/                   # pytest / unittest
├── .github/workflows/       # CI：构建推送镜像 + 同步镜像说明
├── scripts/release.py       # 发布脚本：打 tag 并推送（不推 main）
├── import_novels.py         # CLI 导入
├── run.py                   # 同时拉起前端入口 + 后端 API
├── legado_book_source.json
├── novels/                  # 源 TXT（书源/分类）
├── covers/                  # 封面（thumbs/ 为派生缩略图）
└── data/                    # novels.db、contents/、配置、日志（volume）
```

**books 表**：`title` `author` `category`（`起点-都市`）`intro` `status` `tags` `cover_file`
`source_path` `source_hash` `word_count` `chapter_count` `latest_chapter` `source` `source_id`
`read_percent` `read_chapter_index` `read_at` `created_at` `updated_at`

**chapters 表**：`book_id` `index` `title` `content_offset` `content_length` `content_chars`
（正文在 `data/contents/{book_id}.bin`，遗留 `content` 列仅作兼容）

**运行时配置文件**：`data/auth.json`、`data/scraper_settings.json`、
`data/webdav_settings.json`、`data/maintenance_settings.json`。

---

## 开发与测试

```bash
# 后端测试
python -m pytest tests/ -q
python -m unittest tests.test_core

# 前端类型检查与构建
cd frontend
npm run typecheck
npm run build
```

CI（推送 `v*` 发布标签或手动触发）会先跑后端 `pytest` 与前端构建，任一失败则不推送镜像。

### 发布流程

代码推送与镜像发布已解耦：推 `main` **只推代码**，不触发镜像构建。

```bash
# 日常：只推代码
git add -A
git commit -m "feat: ..."
git push origin main

# 发布：创建并推送 tag，触发镜像构建 + README 同步
python scripts/release.py 1.2.3                    # 指定版本
python scripts/release.py                          # 默认 patch 递增并发布
python scripts/release.py --bump minor --dry-run   # 预览 minor；去掉 --dry-run 即发布
```

脚本会：

1. 检查 tracked 改动已提交、当前在 `main`、`HEAD` 已推送到 `origin/main`
2. 创建 annotated tag `v1.2.3`（可用 `--message` 自定义说明）
3. **只推送该 tag，不推送 main**
4. 由 CI 运行测试、构建推送镜像（`latest` / `1.2.3` / `1.2` / `v1.2.3` / `sha-...`），并同步 README 到镜像页

补充参数：`--run-tests` 在打 tag 前本地跑 pytest；`--force` 跳过安全检查（紧急发布用）；
`--dry-run` 只检查并打印命令。

### Docker 部署要点

- 基础镜像 `python:3.12-slim`，前端多阶段构建（Node → `frontend/dist`）。
- 用户数据一律 volume 挂载，不打进镜像。
- 默认使用 `network_mode: host`，便于直达宿主机 Chrome CDP；不需要浏览器刮削时可改为端口映射：

```yaml
    ports:
      - "7311:7311"
      - "7312:7312"
```

### 镜像与自动构建

- 镜像：`iamplusdev/novel-server`，架构 `linux/amd64`。
- 标签：`latest`、`v1.2.3`、`1.2.3`、`1.2`、`sha-<短哈希>`。
- 触发：**仅推送 `v*` 发布标签**或手动运行；推 `main` 只推代码，不构建镜像。
- **README 随发布 tag 同步为 Docker Hub 镜像说明**（不再由 main 的 README 变更触发）。
- Secrets：`DOCKERHUB_USERNAME`、`DOCKERHUB_TOKEN`。
- 工作流：`.github/workflows/docker-publish.yml`、`update-dockerhub-description.yml`。

---

## 维护与备份

应用内暂未提供备份 / 恢复 UI。数据目录已挂载到宿主机时，建议使用宿主机定时快照
或异机备份；也可手动打包：

```bash
# 备份（SQLite、正文包、封面、账号、配置）
tar czf novel-data-$(date +%F).tar.gz data covers novels

# 恢复：先停服、解包覆盖、再启动
docker compose down
tar xzf novel-data-YYYY-MM-DD.tar.gz
docker compose up -d
```

> SQLite 运行中直接复制可能不一致，重要备份建议先停服，或使用宿主机文件系统快照。

- 源 TXT 未变化时重复导入几乎无开销（SHA256 跳过）。
- 正文包采用「临时包写入 → DB 提交 → 原子替换」，中断不会错乱。
- 升级：`docker compose build && docker compose up -d`，卷数据保留；或 `docker compose pull` 使用预构建镜像。
- 离线部署到 NAS：
  ```bash
  docker save -o novel-server-latest.tar novel-server:latest
  # NAS 上：docker load -i novel-server-latest.tar
  ```
- 排查：`docker compose logs -f`，或设 `LOG_FILE=1` 落盘 `data/novel-server.log`。
- 勿将密码、恢复码、WebDAV 凭据提交进仓库。

---

## 安全建议

- 公网部署使用 HTTPS，并设 `COOKIE_SECURE=1`。
- 设置 `READ_API_KEY`，否则 Legado 无法通过读鉴权访问。
- 需要按域名生成绝对链接时配置 `TRUSTED_HOSTS`，避免 Host 头注入。
- 管理员账号仅单用户；请保存恢复码，泄露后尽快改密。
- WebDAV 密码保存在 `data/webdav_settings.json`（0600），请保护数据目录。

---

## 常见问题

- **书源 / API 页地址显示 `127.0.0.1:7311`**
  后端基址取自 `PUBLIC_BASE_URL`，且 compose 的 `environment:` 会覆盖 `.env`。改成域名或设 `TRUSTED_HOSTS`，重建后到 Legado 删除旧书源重新导入。

- **导入后没有章节 / 无法分章**
  确认 TXT 在 `novels/<书源>/<分类>/` 或 `novels/未分类/`（根目录不扫描）；编码会自动择优。已入库但分章错误时，用「体检 → 修复 → 重新解析」。

- **Legado 提示 401 / 读不到**
  公网需设 `READ_API_KEY`；使用后台下载的书源（已自动注入 `header.X-Api-Key`）。

- **改了 `.env` 不生效**
  compose 的 `environment:` 优先级更高，优先改 compose，或改成引用 `${VAR}`。

- **WebDAV 同步找不到远程文件**
  在书库详情 →「进度同步」查看实际文件名。文件名由「书名_作者」决定，需与 Legado 完全一致；同时确认 Legado 已开启「同步阅读进度」。

- **详情页显示远端未更新**
  Legado 只在启动或打开书籍时拉取。若两端都刚读过，按 `durChapterTime` 最新者优先；可在详情页手动拉取查看结果。

- **封面缩略图 404 / 显示原图**
  未安装 Pillow 时 `/thumbs` 自动回退原封面。安装后重启即可：`pip install Pillow`；
  也可在「体检 → 重建缩略图」批量回填。

- **阅读统计没有日 / 周趋势**
  当前只记录每本书最近一次阅读时间（`read_at`）和进度，不做逐日阅读历史；
  统计页展示的是现有数据概览。

- **自动体检没有自动导入**
  自动体检只执行重复 / 异常检查，不会扫描导入源 TXT；需要新书时请手动运行导入。

- **批量刮削被拒 / 频繁 403**
  在「设置 → 刮削参数」调大书间间隔或长休息，减小「每 N 本长休息」；API 侧已内置限速与退避重试。

- **端口 / 反向代理**
  host 网络下服务直接监听 `HOST:PORT`；反代透传 `Host` 与 `X-Forwarded-Proto`，HTTPS 下设 `COOKIE_SECURE=1`。

## License

个人使用，按需自改。
