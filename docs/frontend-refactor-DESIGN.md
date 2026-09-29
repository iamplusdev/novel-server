# 前端重构设计（Vue3 + Vite + Element Plus + Pinia + Vue Router）

> 目标：将原 Vanilla 单页后台重写为可维护的 Vue3 SPA，API 契约保持不变。
> **状态（P8）**：Vue 前端已全面接管，旧 `index.html` / `admin.css` / `admin.js` / `admin.ui.js` 已删除。

## 1. 风格锚点

- **产品感**：个人书库管理台（偏 Notion / Calibre Web 的安静工具感），非营销站。
- **UI 基线**：Element Plus 默认主题 + 轻微微调（圆角、侧栏底色、暗色模式）。
- **不追求**：复杂动效、插画、品牌视觉；优先信息密度与操作效率。

## 2. 色板与字体

| 角色 | 值 | 说明 |
|---|---|---|
| 背景 | `#f5f7fa` / 暗色 `#0f1419` | 页面底 |
| 侧栏 | `#ffffff` / 暗色 `#1a2332` | 导航容器 |
| 主文字 | `#303133` / 暗色 `#e5eaf3` | |
| 弱文字 | `#909399` | 辅助说明 |
| 强调色 | Element Primary `#409eff` | 主按钮 / 链接 |
| 危险 | `#f56c6c` | 删除 / 停止 |
| 成功 | `#67c23a` | 完成态 |

字体：系统栈 `-apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif`；代码/路径用 `ui-monospace, Consolas, monospace`。

## 3. 技术架构

```
frontend/                     # Vite + Vue3 + TS
  src/
    api/                      # fetch 封装、类型、各域 API
    stores/                   # Pinia：auth / library / theme / scrape / import
    layouts/AdminLayout.vue   # 侧栏 + 主区
    views/                    # 路由页
    components/               # 书卡、筛选栏、SSE 日志等
    router/index.ts
    main.ts
  dist/                       # 构建产物（Docker 运行时拷贝）

app/main.py                   # 仅 API（默认 :7312）
app/frontend_server.py        # 前端静态 + /api 反代（默认 :7311）
run.py                        # 同时拉起前后端双端口
Dockerfile                    # 多阶段：node 构建 → python 运行
```

**开发**：`cd frontend && npm run dev`（Vite proxy → `http://127.0.0.1:7312`）  
**生产**：`npm run build` 后 `python run.py`；前端 `:7311` 托管 dist 并反代 `/api` → 后端 `:7312`。

## 4. 路由与页面清单

| 路径 | 视图 | 对应旧 UI | 功能要点 | 交付阶段 |
|---|---|---|---|---|
| `/login` | LoginView | `#login` | 登录 / 首次初始化 / 忘记密码 / 恢复码展示 | P2 |
| `/` | LibraryView | `#view-library` | 书源/分类筛选、搜索、排序、卡片墙、分页 | P3 |
| `/books/:id` | BookDetailView | 抽屉 `#drawer` | 详情编辑、封面上传、删除 | P4 |
| （库内弹窗） | ScrapeDialog | `#scrape-modal` | 刮削搜索 / 详情 / 采用 | P5 |
| `/import` | ImportView | `#view-import` | 本地导入、SSE 进度、停止 | P6 |
| `/check` | CheckView | `#view-check` | 体检报告、合并、修复、归位、一键刮削 | P6–P7 |
| `/api-docs` | ApiView | `#view-api` | 服务地址、公开 API、Legado 书源下载 | P7 |
| `/settings` | SettingsView | `#view-settings` | 主题、改密、退出、运行环境 | P7 |

## 5. 状态与 API 层

- **auth store**：`status` / `username` / `token`（仅内存，会话靠 HttpOnly Cookie）/ 登录、登出、改密。
- **library store**：列表查询参数（q/category/source/tag/sort/page）、items、total、stats。
- **theme store**：`auto | light | dark`，写入 `localStorage` 并切换 `html.dark`。
- **api/client.ts**：统一 `fetch`，带 `credentials: 'include'`；401 跳转登录；业务错误抛 `ApiError`。
- **SSE**：`EventSource` 封装为可取消 Promise/回调（导入流 `/api/admin/import/stream`、批量刮削流 `/api/admin/scrape/batch/stream`）。

### 关键 API（保持不变）

```
GET  /api/auth/status|me
POST /api/auth/setup|login|logout|change-password|forgot
GET  /api/admin/stats|tags|books|books/{id}|duplicates
PATCH/DELETE /api/admin/books/{id}
POST /api/admin/books/{id}/cover
POST /api/admin/import|import/cancel
GET  /api/admin/import/status|stream
POST /api/admin/scrape/search|detail|books/{id}/apply
POST /api/admin/scrape/batch/start|cancel
GET  /api/admin/scrape/batch/status|stream
GET  /api/admin/library/report
POST /api/admin/library/merge|repair|repair/{id}|relocate
GET  /api/legado/book-source
```

## 6. 部署

- Docker 多阶段：`node:22-alpine` 构建 `frontend/` → `python:3.12-slim` 拷贝 `dist` + `app`。
- 体积数据（data/covers/novels）仍挂 volume，不进镜像。
- 旧 Vanilla 文件在 P8 删除前保留于仓库，便于回滚。

## 7. 分阶段交付（每阶段：实现 → 测试 → git commit）

| 阶段 | 内容 | 验收 |
|---|---|---|
| **P1** | DESIGN.md、Vite 脚手架、布局壳、路由、构建/托管/Dockerfile | `npm run build` 成功；后端能托管 dist |
| **P2** | API client、auth store、登录/初始化/找回/改密 | 流程可走通，401 守卫生效 |
| **P3** | 书库列表、筛选、搜索、分页、卡片 | 与旧列表数据一致 |
| **P4** | 详情编辑、封面、删除 | 读写/删除成功 |
| **P5** | 单本刮削弹窗 | 搜索/采用可用 |
| **P6** | 导入 + 批量刮削（SSE） | 进度与停止正常 |
| **P7** | 体检、API 书源、设置、主题 | 功能齐全 |
| **P8** | 删除旧 Vanilla、全量回归、文档 | 无旧文件引用 |

## 8. 兼容与风险

- **Cookie 会话**：开发态 Vite proxy 需 `changeOrigin` + 保持 Cookie；生产同源无此问题。
- **SPA fallback**：勿把 `/api`、`/covers`、`/legado_book_source.json`、`/favicon.ico` 误判为前端路由。
- **SSE**：生产经反代时注意 `proxy_buffering off`（Nginx）；当前部署为直连 uvicorn，无此问题。
- **主题**：Element Plus 暗色需 `html.dark` + `@dark` 变量，与旧主题键 `novel_theme_mode` 对齐。
