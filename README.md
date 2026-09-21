# Personal Novel Library

个人 TXT 小说库服务器：FastAPI + SQLite + 原生 HTML/JS 管理后台 + Legado 书源。

目标：极简、零多余依赖、可长期在个人服务器 / NAS 上维护。

## 功能

- 扫描 `novels/<分类>/*.txt`，解析章节写入 SQLite（内容哈希未变则跳过）
- JSON API：分类浏览、搜索、书籍详情、目录、正文
- Legado（开源阅读）自定义书源：发现页分类、搜索、详情、目录、正文，**全部返回完整 URL**
- 管理后台（`/admin`）：Token 鉴权；维护封面/书名/作者/简介/状态/标签；上传封面；删除书籍；触发导入
- 封面存本地 `covers/`，由服务直接提供

## 技术栈与依赖

| 组件 | 选型 |
|------|------|
| Web | FastAPI + Uvicorn |
| 数据库 | SQLite + SQLAlchemy 2.x |
| 前端 | 原生 HTML / CSS / JS（无框架） |
| 依赖 | `fastapi` `uvicorn[standard]` `sqlalchemy` `python-multipart` |

## 项目结构

```text
novel-server/
├── app/
│   ├── main.py            # FastAPI 入口、静态路由
│   ├── config.py          # 环境变量配置 + 分类常量
│   ├── database.py        # SQLAlchemy 引擎 / 会话
│   ├── models.py          # Book / Chapter
│   ├── parsers.py         # TXT 章节与文件名解析
│   ├── importer.py        # 目录扫描与增量导入
│   ├── auth.py            # 管理 Token 校验
│   ├── serializers.py     # Book/Chapter → JSON
│   └── routers/
│       ├── public.py      # 公开阅读 API
│       ├── legado.py      # Legado 书源 API
│       └── admin.py       # 管理后台 API
├── index.html             # 管理后台 SPA
├── admin.css / admin.js
├── import_novels.py       # CLI 导入
├── run.py                 # 服务启动
├── legado_book_source.json
├── requirements.txt
├── Dockerfile / docker-compose.yml
├── deploy/novel-server.service
├── novels/                # 源 TXT（按分类子目录）
├── data/novels.db         # SQLite
└── covers/                # 封面图片
```

## 数据库设计

### books

| 字段 | 说明 |
|------|------|
| id | 主键 |
| title / author | 书名、作者 |
| category | 分类（与文件夹同名） |
| intro / status / tags | 简介 / 连载·完结·未知 / 逗号分隔标签 |
| cover_file | covers 目录下文件名 |
| source_path / source_hash | 源文件路径与 SHA256（增量导入） |
| word_count / chapter_count / latest_chapter | 统计 |
| created_at / updated_at | ISO 时间 |

### chapters

| 字段 | 说明 |
|------|------|
| id | 主键 |
| book_id | 外键 → books.id，删除书籍级联删除 |
| index | 章序（从 0 起） |
| title | 章节标题 |
| content | 章节全文 TEXT |

索引：`books.category/title/author`，`chapters(book_id, index)`。

## 推荐 TXT 目录约定

```text
novels/
├── 玄幻/
│   └── 书名.txt                 # 或 书名(作者).txt / 作者-书名.txt
├── 仙侠/
├── 都市/
└── ...
```

- 无法识别的根目录 txt → 分类「未分类」
- 章节识别支持：`第X章/节/回/卷/篇`、`Chapter N`、`序章/楔子/番外/终章` 等
- 编码自动尝试 UTF-8 / GB18030 / Big5

## API 定义

公开（默认无鉴权，适合内网；如需隔离可在网关加认证）：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/categories` | 分类及数量 |
| GET | `/api/books` | 列表：`category` `q` `status` `sort` `page` `page_size` |
| GET | `/api/search?q=` | 搜索（书名/作者/标签/简介） |
| GET | `/api/books/{id}` | 详情 |
| GET | `/api/books/{id}/chapters` | 章节目录（可分页） |
| GET | `/api/books/{id}/chapters/{chapter_id}` | 正文 |

Legado（返回绝对 URL）：

| 方法 | 路径 |
|------|------|
| GET | `/api/legado/explore/{分类}?page=` |
| GET | `/api/legado/search?q=&page=` |
| GET | `/api/legado/book/{id}` |
| GET | `/api/legado/toc/{id}` |
| GET | `/api/legado/content/{book_id}/{chapter_id}` |
| GET | `/api/legado/book-source` | 生成注入了 `PUBLIC_BASE_URL` 的书源 JSON |

管理（`Authorization: Bearer $ADMIN_TOKEN`）：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/stats` | 统计 |
| GET | `/api/admin/books` | 管理列表 |
| GET/PATCH | `/api/admin/books/{id}` | 详情 / 更新元数据 |
| POST | `/api/admin/books/{id}/cover` | multipart 上传封面 |
| DELETE | `/api/admin/books/{id}` | 删除书籍（级联章节+封面） |
| POST | `/api/admin/import` | 后台触发导入 |
| GET | `/api/admin/import/status` | 导入状态 |

OpenAPI 文档：`/docs`

## 配置

复制 `.env.example` 为环境变量或 `.env`（systemd 可用 `EnvironmentFile`）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `ADMIN_TOKEN` | `change-me` | **必改**，管理后台 Token |
| `PUBLIC_BASE_URL` | `http://127.0.0.1:8000` | **必改**，手机可访问的完整根地址 |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | 监听 |
| `NOVELS_DIR` | `./novels` | TXT 根目录 |
| `DATABASE_PATH` | `./data/novels.db` | SQLite 路径 |
| `COVERS_DIR` | `./covers` | 封面目录 |

## 本地运行

```bash
cd novel-server
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt

# 配置 Token 与局域网地址（PowerShell 示例）
$env:ADMIN_TOKEN = "please-change-me"
$env:PUBLIC_BASE_URL = "http://192.168.1.100:8000"

# 导入 TXT
python import_novels.py

# 启动
python run.py
```

- 管理后台：`http://<host>:8000/admin`
- API 文档：`http://<host>:8000/docs`

也可在后台再次导入：管理页「导入」或 `python import_novels.py --watch`。

## Legado 书源接入

1. 确保手机与服务器同一局域网，`PUBLIC_BASE_URL` 可访问。
2. 浏览器打开 `http://<host>:8000/legado_book_source.json`，或在管理后台「API / 书源」复制。
3. 把 `bookSourceUrl` 改成你的地址（后台复制时已自动填入）。
4. Legado → 我的 → 书源管理 → 本地导入 / 网络导入。
5. 发现页可浏览各分类；搜索、详情、目录、正文均走 JSON API。

示例响应字段（JsonPath 规则已匹配）：

- 探索/搜索：`$.books[].name/author/cover_url/intro/toc_url`
- 详情：`$.name/author/cover_url/intro/toc_url`
- 目录：`$.chapters[].name/content_url`
- 正文：`$.content`

## 部署

### 方式 A：Docker（推荐 NAS）

```bash
# 编辑 docker-compose.yml 中的 ADMIN_TOKEN 与 PUBLIC_BASE_URL
docker compose up -d --build

# 导入（容器内）
docker compose exec novel-server python import_novels.py
```

### 方式 B：systemd（Linux 主机）

```bash
sudo useradd -r -s /usr/sbin/nologin novel || true
sudo mkdir -p /opt/novel-server
sudo rsync -a ./ /opt/novel-server/
cd /opt/novel-server
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt

cat | sudo tee /opt/novel-server/.env <<'EOF'
ADMIN_TOKEN=please-change-me
PUBLIC_BASE_URL=http://192.168.1.100:8000
HOST=0.0.0.0
PORT=8000
NOVELS_DIR=/opt/novel-server/novels
DATABASE_PATH=/opt/novel-server/data/novels.db
COVERS_DIR=/opt/novel-server/covers
EOF
sudo chown -R novel:novel /opt/novel-server
sudo cp deploy/novel-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now novel-server
sudo -u novel /opt/novel-server/.venv/bin/python /opt/novel-server/import_novels.py
```

### 局域网与内网穿透

- 局域网：手机访问 `http://<服务器IP>:8000`，书源 `bookSourceUrl` 同此。
- 防火墙放行 TCP 8000。
- 外网访问（可选）：frp / Cloudflare Tunnel / Tailscale 等，将 `PUBLIC_BASE_URL` 改为穿透后的 HTTPS 地址；Legado 若走外网建议再加反向代理 Basic Auth，并在书源 `header` 中带认证信息。

## 管理后台

1. 打开 `/admin`，输入 `ADMIN_TOKEN`。
2. 书库：封面墙/列表、搜索筛选、点击卡片编辑元数据、上传封面、删除。
3. 导入：一键扫描 `NOVELS_DIR`，查看新增/更新/跳过/失败日志。
4. API / 书源：查看接口与复制 Legado JSON。

## 维护建议

- 源 TXT 只增不改时，重复导入几乎无开销（SHA256 跳过）。
- 备份：打包 `data/` + `covers/` 即可；`novels/` 另存。
- 升级：拉代码 → `pip install -r requirements.txt` → 重启服务。
- 不要把真实 `ADMIN_TOKEN` 提交到仓库。

## License

个人使用，按需自改。
