# 大模型对话台（LLM Web · Python + Django）

一个用 **Python + Django** 写的大模型 Web 对话界面：在网页上配置任意 **OpenAI 兼容接口**（vLLM、Ollama、Xinference、One-API，或 DeepSeek、智谱 GLM、OpenAI 等云服务），即可进行多轮流式对话。自带用户登录、连接测试、联网搜索等功能，适合个人/内网部署自己的大模型。

- 后端：Django（MTV），不依赖 Django REST Framework，前端为原生 HTML/CSS/JS，无 Node 构建步骤
- 模型对接：仅用 `requests` 调用 OpenAI 兼容的 `/chat/completions`，SSE 流式输出
- 存储：SQLite（零配置），配置与用户账号都在本地数据库中

---

## 目录

- [功能特性](#功能特性)
- [技术栈与版本](#技术栈与版本)
- [目录结构详解（每个文件是干嘛的）](#目录结构详解每个文件是干嘛的)
- [快速开始](#快速开始)
- [如何登录](#如何登录)
- [如何设置 API 接入](#如何设置-api-接入)
- [页面与后端接口说明](#页面与后端接口说明)
- [部署到生产环境前必改](#部署到生产环境前必改)
- [常见问题与踩坑记录](#常见问题与踩坑记录)
- [提交到 GitHub 的步骤](#提交到-github-的步骤)

---

## 功能特性

- 💬 **流式对话**：逐字输出（SSE），支持中途「停止生成」、开新对话
- 🔐 **登录鉴权**：全站默认拒绝匿名访问；页面请求 302 跳登录页，API 请求返回 401 JSON
- 🔌 **任意 OpenAI 兼容后端**：vLLM / Ollama / Xinference / LocalAI / One-API / 各类云厂商
- 🧪 **一键测试连接**：先探测 `GET /models`，不可用则自动降级为发一条最小对话验证
- 🔍 **联网搜索开关**：支持智谱 GLM 的 `web_search` 工具（需模型服务支持，其他服务会自动忽略）
- 🛡️ **输入校验**：历史消息条数/长度限制、角色白名单、Temperature 范围校验、CSRF 防护
- 🈶 **中文友好**：强制 UTF-8 解码，修复部分推理服务（如 vLLM）SSE 响应不带 charset 导致的中文乱码
- 🚫 **误填地址识别**：把模型地址误填成本网站时（常见 8000 端口冲突），给出明确提示而不是空回复

## 技术栈与版本

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.10+（开发环境 3.13） | 见 `requirements.txt` |
| Django | 5.x / 6.x（`>=5.0,<7.0`） | Web 框架 |
| requests | >= 2.31 | 调用模型 HTTP 接口 |
| 数据库 | SQLite | Django 自带，无需安装 |

---

## 目录结构详解（每个文件是干嘛的）

```
LLM_Web_Py_Django/
├── manage.py                 # Django 命令行入口（启动、迁移、建用户都靠它）
├── requirements.txt          # Python 依赖清单（Django、requests）
├── README.md                 # 本文件
├── .gitignore                # Git 忽略规则（虚拟环境、数据库、IDE 文件等）
├── db.sqlite3                # SQLite 数据库文件（运行迁移后生成，已被 gitignore，不提交）
│
├── .venv/                    # Python 虚拟环境（已被 gitignore，不提交）
├── .idea/                    # PyCharm 工程配置（已被 gitignore，不提交）
│
├── llm_web/                  # 【项目包】Django 全局配置（项目名 llm_web）
│   ├── __init__.py           # 包标识，空文件
│   ├── settings.py           # 全局配置：注册 app、中间件、数据库、语言时区、登录跳转地址
│   ├── urls.py               # 根路由：/admin/、/accounts/（登录登出）、/（chat 应用）
│   ├── middleware.py         # LoginRequiredMiddleware：全站登录拦截（页面 302 / API 401）
│   ├── wsgi.py               # WSGI 部署入口（传统服务器用，如 gunicorn / mod_wsgi）
│   └── asgi.py               # ASGI 部署入口（异步服务器用，当前为同步视图，预留）
│
└── chat/                     # 【主应用】大模型对话的全部业务逻辑
    ├── __init__.py           # 应用包标识，空文件
    ├── apps.py               # 应用配置类 ChatConfig（应用名、verbose_name）
    ├── models.py             # ApiConfig 模型：保存 Base URL / API Key / 模型名等（单例）
    ├── views.py              # 视图层：对话页、设置页、/api/chat 流式接口、/api/test 测试接口
    ├── llm_client.py         # 【核心】模型调用封装：SSE 流式解析、连接探测、错误信息提取
    ├── urls.py               # 应用路由：""、settings/、api/chat/、api/test/
    ├── admin.py              # 后台注册 ApiConfig，可在 /admin/ 直接改配置
    ├── migrations/
    │   ├── __init__.py       # 迁移包标识
    │   └── 0001_initial.py   # 由 makemigrations 生成的建表迁移（对应 ApiConfig）
    └── templates/            # 模板目录（APP_DIRS 自动发现）
        ├── chat/
        │   ├── base.html       # 公共布局：顶部导航栏（对话/设置/退出登录）、全局样式
        │   ├── index.html      # 对话主页：消息气泡、输入框、流式渲染、停止、联网搜索开关
        │   └── settings.html   # 模型配置表单：保存 + 测试连接（含结果提示）
        └── registration/
            └── login.html      # 登录页（覆盖 Django 自带登录模板，中文界面）
```

> **分层约定**：`views.py` 只负责 HTTP 协议、参数校验和错误码映射；真正调用大模型的逻辑全部在 `llm_client.py`，它不依赖 Django 的 `request`，方便单独测试和复用。

### 关键代码导览

| 想了解 | 看哪里 |
| --- | --- |
| 请求是怎么发给模型的、SSE 怎么解析 | `chat/llm_client.py` 的 `chat_completions_stream()` |
| 中文乱码、重定向误填是怎么处理的 | `chat/llm_client.py` 中 `resp.encoding = "utf-8"`、`_redirect_error()` |
| 测试连接做了什么 | `chat/llm_client.py` 的 `test_connection()`（先 `/models` 后最小对话） |
| 配置存在哪、怎么保证只有一份 | `chat/models.py` 的 `ApiConfig.get_config()`（取 id 最小的记录） |
| 哪些路径不需要登录 | `llm_web/middleware.py` 的 `PUBLIC_PREFIXES` |
| 前端如何流式接收/中断 | `chat/templates/chat/index.html`（`fetch` + `ReadableStream` + `AbortController`） |

---

## 快速开始

> 以下命令在 Windows PowerShell 中执行；macOS / Linux 把激活脚本换成 `source .venv/bin/activate` 即可。

### 1. 获取代码并进入目录

```powershell
git clone https://github.com/<你的用户名>/<仓库名>.git
cd LLM_Web_Py_Django
```

### 2. 创建并激活虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

如果 PowerShell 提示"无法执行脚本"，先执行一次（仅当前用户放开）：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 3. 安装依赖

```powershell
pip install -r requirements.txt
```

### 4. 初始化数据库

```powershell
python manage.py migrate
```

### 5. 创建登录账号（必须，否则进不去）

```powershell
python manage.py createsuperuser
```

按提示输入用户名、密码（邮箱可直接回车跳过）。该账号同时能登录 `/admin/` 后台。

### 6. 启动开发服务器

```powershell
python manage.py runserver
```

看到 `Starting development server at http://127.0.0.1:8000/` 即成功，浏览器打开 <http://127.0.0.1:8000/> 会自动跳到登录页。

---

## 如何登录

1. 访问任意页面（如 <http://127.0.0.1:8000/>），未登录会自动跳转到 `/accounts/login/`
2. 输入 `createsuperuser` 创建的用户名和密码
3. 登录成功后进入对话主页；右上角可点「退出登录」
4. 想再开普通账号有两种方式：
   - 后台管理：登录 <http://127.0.0.1:8000/admin/> → 用户（Users）→ 增加用户
   - 命令行：`python manage.py createsuperuser`（建的是超级用户）

**说明：**
- 本项目**没有注册页**，账号由管理员创建，适合个人/团队内网使用
- 会话过期或未登录时：网页操作会跳登录页；前端调接口会收到 `401`，页面提示重新登录
- `/admin/` 由 Django admin 自行鉴权，不在自定义中间件的拦截逻辑内

---

## 如何设置 API 接入

登录后点顶部导航的 **「设置」**（或直接访问 `/settings/`）。

### 需要填写的字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| 接口地址（Base URL） | 是 | OpenAI 兼容服务的基础地址，需以 `http://` 或 `https://` 开头，**不要**带 `/chat/completions` 后缀 |
| API Key | 本地服务可留空 | 云端服务必填；本地部署（Ollama/vLLM）无鉴权时留空 |
| 模型名称 | 是 | 服务里的模型 ID，要与服务端实际加载的名字**完全一致** |
| Temperature | 否 | 0 ~ 2，越大越发散，默认 0.7 |
| 最大 Token 数 | 否 | 留空则不传给服务端，使用服务端默认值 |
| 系统提示词 | 否 | 每轮对话自动置顶的 system 消息 |

操作顺序：建议先点 **「测试连接」**，看到成功提示后再 **「保存」**。测试用的是页面上当前填写的内容，保存才会写入数据库。

### 常见服务的 Base URL 示例

| 模型服务 | Base URL | 模型名示例 | API Key |
| --- | --- | --- | --- |
| vLLM（本地） | `http://localhost:8001/v1` | 部署时 `--served-model-name` 的名字 | 留空 |
| Ollama（本地） | `http://localhost:11434/v1` | `qwen2.5:7b` | 留空 |
| Xinference / LocalAI | `http://localhost:9997/v1`（按实际端口） | 启动时的模型 UID/名 | 留空 |
| One-API / New-API | `http://localhost:3000/v1` | 渠道里配置的模型名 | 令牌 |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | 平台申请 |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` | 平台申请 |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | sk-... |

> 智谱的 **联网搜索** 开关：对话页左下角勾选「🔍 联网搜索」后，该轮请求会带上 `web_search` 工具参数，服务端先实时检索再回答。其他不支持该参数的服务会忽略它，不影响普通对话。

### 配置存在哪？安全吗？

- 配置保存在 `db.sqlite3` 的 `chat_apiconfig` 表中，**API Key 是明文存储**
- 因此 `db.sqlite3` 已加入 `.gitignore`，**不会**被提交到 GitHub
- 生产环境建议改用 PostgreSQL 并对密钥做加密，或通过环境变量注入

### 也可以在后台改配置

访问 `/admin/` → 「API 配置」，直接编辑数据库中的那条记录（全站取最早创建的一条生效）。

---

## 页面与后端接口说明

### 页面对照

| URL | 视图 | 说明 |
| --- | --- | --- |
| `/accounts/login/` | Django auth | 登录页（自定义中文模板） |
| `/accounts/logout/` | Django auth | 退出登录（POST 表单） |
| `/admin/` | Django admin | 后台管理（用户、API 配置） |
| `/` | `views.index` | 对话主页 |
| `/settings/` | `views.settings_view` | 模型配置页（GET 展示 / POST 保存） |

### 前端调用的内部 API（均需登录，均带 CSRF 校验）

**1. 流式对话**

```
POST /api/chat/
Content-Type: application/json

{
  "messages": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！有什么可以帮你？"}
  ],
  "web_search": false
}
```

返回 `text/event-stream`，每行一条 SSE：

- `data: {"type": "delta", "content": "你"}'` —— 增量文本，拼接到气泡
- `data: {"type": "done"}` —— 结束
- `data: {"type": "error", "content": "..."}` —— 可读错误信息

服务端限制：最多取最近 40 条历史、单条内容截断 20000 字、角色只接受 `user`/`assistant`。

**2. 测试连接**

```
POST /api/test/
{"base_url": "http://localhost:11434/v1", "api_key": "", "model": "qwen2.5:7b"}
```

返回普通 JSON：`{"ok": true, "message": "连接成功，服务上可用的模型：..."}` 或 `{"ok": false, "error": "..."}`。

用 curl 验证（先登录拿 Cookie 太麻烦，建议直接用页面上的「测试连接」按钮）：

```powershell
curl -N -X POST http://127.0.0.1:8000/api/chat/ `
  -H "Content-Type: application/json" `
  -b "sessionid=<你的会话Cookie>" `
  -d '{\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}'
```

---

## 部署到生产环境前必改

`llm_web/settings.py` 当前是**开发配置**，上线前至少修改：

1. **`SECRET_KEY`**：换成随机长字符串，不要使用代码里的占位值（可用 `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` 生成）
2. **`DEBUG = False`**：否则出错时会暴露完整堆栈和源码
3. **`ALLOWED_HOSTS`**：从 `["*"]` 改成实际域名，如 `["chat.example.com"]`
4. 用 `collectstatic` + Nginx 托管静态文件，Python 端用 **gunicorn / uwsgi + WSGI**（`llm_web/wsgi.py`）部署，不要直接用 `runserver`
5. 强烈建议套 HTTPS（Nginx 反代 + 证书），否则 API Key 和会话 Cookie 明文传输
6. 注意：流式接口需要 Nginx 关闭缓冲（代码已设置响应头 `X-Accel-Buffering: no`，一般无需额外配置）

---

## 常见问题与踩坑记录

**1. `python` 命令找不到 / 启动的不是 3.13**
Windows 上可能是 Microsoft Store 的别名或其他 Python。用 `py -3.13 -m venv .venv` 明确指定版本，或直接用虚拟环境里的解释器：`.\.venv\Scripts\python.exe manage.py runserver`。

**2. PowerShell 不让激活虚拟环境（红色报错）**
执行策略限制。运行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 后重开终端；或者不激活，直接用 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`。

**3. 8000 端口冲突：Django 和 vLLM 抢同一个端口**
`runserver` 默认用 8000，vLLM 默认也是 8000。两个不能同时占。两种解法任选：
- 把 Django 换端口：`python manage.py runserver 8001`（此时模型服务留在 8000，Base URL 填 `http://localhost:8000/v1`）
- 或把模型服务换端口，Base URL 跟着改

**4. Base URL 误填成了本网站地址 → 空回复 / 跳登录页**
比如在设置里填了 `http://localhost:8000`（这是 Django 自己）。客户端已禁止自动跟随重定向，会明确提示"请求被 302 重定向到登录页"。正确地址应是模型服务的 `/v1`（见上文表格）。

**5. 返回 401 / 403（Unauthorized / Invalid API key）**
API Key 填错、过期，或云端服务欠费/Key 未开通该模型。本地服务一般留空即可。

**6. 模型名对不上（404 Model not found / model_not_exists）**
模型名必须和服务端实际加载的**完全一致**（大小写、冒号都要对）。点「测试连接」会列出服务端可用模型，从列表里复制最稳妥；Ollama 可用 `ollama list` 查看。

**7. 中文回复乱码**
部分推理服务（vLLM 等）的 SSE 响应头不带 `charset`，`requests` 会按 ISO-8859-1 解码导致乱码。代码中已对响应强制 `resp.encoding = "utf-8"`，如自行改造客户端请保留这一行。

**8. 接口返回的是网页（HTML）而不是流式数据**
地址指向了一个网页（最常见的还是填成本网站了）。页面会直接提示"模型接口返回的是网页而不是流式数据"。Base URL 应到 `/v1` 这一级为止，不要加 `/chat`、`/docs` 等路径。

**9. 打开页面就 403 / CSRF 验证失败**
所有 POST 都需要 CSRF Token（页面通过 `@ensure_csrf_cookie` 下发 Cookie，模板里有 `{% csrf_token %}`）。用 Postman/curl 裸调会被拦属于正常现象；浏览器页面内操作不会有此问题。

**10. 忘记密码 / 想重置账号**
命令行重设：`python manage.py changepassword 用户名`；或新建超级用户：`python manage.py createsuperuser`。

**11. 改过 `models.py` 后配置表没更新**
执行：

```powershell
python manage.py makemigrations
python manage.py migrate
```

**12. 页面提示"未登录或会话已过期，请重新登录"**
登录会话过期了（API 请求收到 401）。重新登录即可；如需调整会话时长，可在 `settings.py` 配置 `SESSION_COOKIE_AGE`。

**13. 还没配置模型就发消息**
页面会收到 SSE 错误："尚未配置模型接口，请先到「设置」页面填写"。先去 `/settings/` 保存配置。

**14. 部署到服务器后样式丢失 / 访问报 DisallowedHost**
分别对应：未执行 `collectstatic`（DEBUG=False 后静态文件由 Nginx 托管）；`ALLOWED_HOSTS` 没加你的域名/IP。

**15. 不小心把 db.sqlite3 提交过怎么办**
数据库里可能含 API Key。先 `git rm --cached db.sqlite3` 停止跟踪并提交，再到模型平台**轮换（重置）该 API Key**——进入过 Git 历史的密钥应视为已泄露。

---

## 提交到 GitHub 的步骤

`.gitignore` 已排除虚拟环境、`db.sqlite3`、`__pycache__`、`.idea/` 等，可放心提交：

```powershell
# 1. 确认要提交的文件里没有 .venv、db.sqlite3
git status

# 2. 初始化并提交（首次）
git init
git add .
git commit -m "init: Django 大模型对话台"

# 3. 在 GitHub 上新建空仓库后，关联并推送
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

推送前自查：
- [ ] `git status` 中**没有** `db.sqlite3`（含 API Key 与密码哈希）
- [ ] **没有** `.venv/`、`__pycache__/`、`.idea/`
- [ ] `settings.py` 里没有生产环境真实密钥（当前为占位符，OK）

---

## 许可证

本项目基于 [MIT License](LICENSE) 开源，可自由使用、修改和分发，保留版权声明即可。
