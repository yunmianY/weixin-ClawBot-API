# 微信 ClawBot API

基于腾讯官方 [OpenClaw](https://docs.openclaw.ai) 开放平台的微信个人号 AI 聊天机器人，支持接入任意 AI 模型，实现微信消息自动回复。

> **免部署、免登录 OpenClaw** — 直接调用官方 iLink API，开箱即用。

---

## 目录

- [快速开始](#快速开始)
- [功能特性](#功能特性)
- [登录流程](#登录流程)
- [AI 提供商](#ai-提供商)
- [配置文件](#配置文件)
- [Bot 指令](#bot-指令)
- [24 小时自动重连](#24-小时自动重连)
- [媒体消息支持](#媒体消息支持)
- [项目结构](#项目结构)
- [API 协议说明](#api-协议说明)
- [注意事项](#注意事项)
- [相关资源](#相关资源)

---

### Python 版（推荐）

**环境要求：** Python 3.9+

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行
python bot.py
```

### Node.js 版

**环境要求：** Node.js 18+

```bash
# 确保 package.json 存在 type: module（已内置则跳过）
echo '{ "type": "module" }' > package.json

# 运行
node bot.js
```

首次运行会引导你选择 AI 提供商并填写配置，之后配置会保存在 `config.json` 中。

---

## 功能特性

| 功能 | 说明 |
|---|---|
| 🔐 扫码登录 | 终端渲染二维码，支持回退链接 |
| 📩 长轮询接收 | 实时获取微信消息 |
| 🤖 AI 自动回复 | 支持多家 AI 提供商，一键切换 |
| ⌨️ 正在输入 | 发送回复前显示"正在输入…" |
| 🔄 梯度重试 | AI 接口失败时自动重试（指数退避） |
| 🔁 24h 自动重连 | 到期预警 → 确认 → 无缝切换，全程不断线 |
| 💬 Bot 指令 | `/help` `/time` `/重新连接` 等内置指令 |
| 📎 媒体支持 | 图片消息接入 vision API，语音消息解码 |
| ⚙️ 可视化配置 | 启动时查看脱敏配置，支持修改/切换 |

---

## 登录流程

```
运行 bot ──→ 选择 AI 提供商 ──→ 确认/配置 API ──→ 扫码登录 ──→ Bot 在线
```

1. 终端打印二维码（需安装 `qrcode[pil]`/`Pillow`），同时提供链接作为备用
2. 手机微信扫码，确认连接
3. 若微信要求数字配对码，在终端输入手机显示的数字
4. 登录成功后终端显示确认信息
5. 给 Bot 发送第一条消息，自动收到指令列表
6. 后续消息均由 AI 自动回复

---

## AI 提供商

| 提供商 | 接口格式 | 默认地址 | 默认模型 |
|---|---|---|---|
| **DusAPI** | Anthropic `/v1/messages` | `https://api.dusapi.com` | `gpt-5` |
| **DeepSeek** | OpenAI `/chat/completions` | `https://api.deepseek.com` | `deepseek-v4-flash` |

两者均兼容同类格式的第三方 API，例如：
- DusAPI 模式可接入 Anthropic 官方 API 及其他 Anthropic 格式代理
- DeepSeek 模式可接入任何 OpenAI-compatible 接口（如 ModelScope、硅基流动等）

---

## 配置文件

`config.json`（首次运行自动生成，**请勿提交到版本控制**）：

```json
{
  "provider": "deepseek",
  "providers": {
    "dusapi": {
      "api_key": "your-dusapi-key",
      "base_url": "https://api.dusapi.com",
      "model": "gpt-5",
      "prompt": "你是一个有帮助的AI助手，请用中文简洁地回复。字数尽量少一些"
    },
    "deepseek": {
      "api_key": "your-deepseek-key",
      "base_url": "https://api.deepseek.com",
      "model": "deepseek-v4-flash",
      "prompt": "你是一个有帮助的AI助手，请用中文简洁地回复。字数尽量少一些"
    }
  }
}
```

每次启动时会显示当前配置概览（API Key 脱敏显示），可选择：

```
  当前选择：DeepSeek
  API Key  : sk-d0*****************************e8c5c
  API 地址 : https://api.deepseek.com
  模型     : deepseek-v4-flash

使用此配置继续？(Y 继续 / N 重新配置 / S 切换提供商):
```

---

## Bot 指令

| 指令 | 功能 |
|---|---|
| `/help` 或 `/指令` | 查看所有可用指令 |
| `/time` | 查询当前连接剩余有效时间 |
| `/重新连接` | 手动触发重连（需回复 Y/N 确认） |

- 首次消息自动推送指令列表
- 非指令内容直接转发给 AI 处理
- 扩展指令只需在消息循环中添加分支并更新 `COMMANDS_MSG` 常量

---

## 24 小时自动重连

iLink 连接有效期为 24 小时，Bot 内置智能续连机制：

```
登录 ──→ 22h 后预警 ──→ 用户确认(Y/N) ──→ 扫码切换 ──→ 新连接生效
                                      │
                              N → 30min 后再问
                              最后 30min → 强制重连
```

### 可调参数

在 `bot.py` / `bot.js` 顶部 `RECONNECT_CONFIG` 中调整：

| 参数 | 说明 | 生产值 | 测试建议值 |
|---|---|---|---|
| `session_duration` | 会话总时长（秒） | `86400` | `300` |
| `warning_before` | 提前预警时间（秒） | `7200` | `60` |
| `reminder_interval` | 拒绝后重问间隔（秒） | `1800` | `30` |
| `force_before` | 强制重连阈值（秒） | `1800` | `60` |
| `qrcode_scan_timeout` | 扫码等待超时（秒） | `600` | `120` |

---

## 媒体消息支持

Bot 支持接收并处理微信媒体消息：

| 类型 | 处理方式 |
|---|---|
| 🖼️ 图片 | CDN 下载 → AES-128-ECB 解密 → 缩放/转码 → 送入 vision API 让 AI 理解 |
| 🎤 语音 | CDN 下载 → AES 解密 → SILK v3 解码 → WAV（需安装 `pilk`） |

媒体处理模块 `media.py` 提供完整的下载、解密、转码、图片预处理工具链。

---

## 项目结构

```
.
├── bot.py              # Python 实现（推荐）
├── bot.js              # Node.js 实现
├── dusapi.py           # DusAPI / Anthropic 格式接口封装
├── deepseek.py         # DeepSeek / OpenAI 格式接口封装
├── media.py            # 媒体文件处理（下载/解密/图片/语音）
├── requirements.txt    # Python 依赖
├── config.json         # 配置文件（自动生成，勿提交）
├── weixin-bot-api.md   # iLink Bot API 参考文档
├── weixin-openclaw-api-py-docs.md  # OpenClaw Python SDK 文档
└── README.md
```

---

## API 协议说明

### 请求头

```
Content-Type: application/json
AuthorizationType: ilink_bot_token
X-WECHAT-UIN: <随机 uint32 → base64>
iLink-App-Id: bot
Authorization: Bearer <bot_token>
```

### 消息收发流程

```
POST /getupdates  (长轮询, 35s hold)
  └─ 收到消息
       ├─ Bot 指令匹配 → 返回内置回复
       ├─ 重连确认 → 处理 Y/N
       └─ AI 回复流程:
            POST /getconfig   → 获取 typing_ticket
            POST /sendtyping  → "正在输入" (status=1)
            AI API 调用       → 生成回复
            POST /sendmessage → 发送消息
            POST /sendtyping  → 结束输入 (status=2)
```

### sendmessage 结构

官方要求 `sendmessage` 包含完整字段，否则消息静默丢失（HTTP 200 但不投递）：

```json
{
  "msg": {
    "from_user_id": "",
    "to_user_id": "<用户ID@im.wechat>",
    "client_id": "openclaw-weixin-<随机hex>",
    "message_type": 2,
    "message_state": 2,
    "context_token": "<从收到的消息中获取>",
    "item_list": [{ "type": 1, "text_item": { "text": "回复内容" } }]
  },
  "base_info": {
    "channel_version": "2.4.3",
    "bot_agent": "weixin-ClawBot-API/1.0.1 (python)"
  }
}
```

> ⚠️ `context_token` 必须使用当前消息中的值，不可复用旧 token。

---

## 注意事项

1. **Bot ID 会变化** — 每次扫码登录都会分配新的 Bot ID，这是 iLink 平台的设计特性
2. **合规使用** — 需遵守《微信 ClawBot 功能使用条款》，腾讯保留内容过滤和限速权利
3. **仅支持文本 + 图片理解** — 语音、视频等媒体类型的*发送*需额外实现 CDN 加密上传流程
4. **非核心业务** — 该服务可能随时变更或终止，不建议用于关键业务场景
5. **保护密钥** — `config.json` 含 API Key，已在 `.gitignore` 中排除

---

## 相关资源

- [OpenClaw 官方文档](https://docs.openclaw.ai)
- [@tencent-weixin/openclaw-weixin (npm)](https://www.npmjs.com/package/@tencent-weixin/openclaw-weixin)
- [DusAPI — 多模型 AI 接口](https://dusapi.com)
- [DeepSeek API](https://api.deepseek.com)
- [GitHub Releases — 打包 EXE](https://github.com/SiverKing/weixin-ClawBot-API/releases)
