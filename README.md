<div align="center">
  <a href="https://github.com/LiteSuggarDEV/nonebot_plugin_suggarchat/">
    <img src="https://github.com/user-attachments/assets/b5162036-5b17-4cf4-b0cb-8ec842a71bc6" width="200" alt="SuggarChat Logo">
  </a>
  <h1>SuggarChat</h1>
  <h3>基于 AmritaCore 的轻量完整聊天智能体插件</h3>

  <p>
    <a href="https://pypi.org/project/nonebot-plugin-suggarchat/">
      <img src="https://img.shields.io/pypi/v/nonebot-plugin-suggarchat?color=blue&style=flat-square" alt="PyPI Version">
    </a>
    <a href="https://www.python.org/">
      <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&style=flat-square" alt="Python Version">
    </a>
    <a href="https://nonebot.dev/">
      <img src="https://img.shields.io/badge/nonebot2-2.4.0+-blue?style=flat-square" alt="NoneBot Version">
    </a>
    <a href="LICENSE">
      <img src="https://img.shields.io/github/license/LiteSuggarDEV/nonebot_plugin_suggarchat?style=flat-square" alt="License">
    </a>
    <a href="https://qm.qq.com/q/PFcfb4296m">
      <img src="https://img.shields.io/badge/QQ%E7%BE%A4-1002495699-blue?style=flat-square" alt="QQ Group">
    </a>
  </p>
</div>

## ✨ 特性一览

> 本插件定位为**轻量完整的聊天智能体**，面向日常聊天场景；
> 如需体验完整的 Agent 编排能力（复杂工具链、任务编排等），请迁移至 [AmritaBot](https://github.com/AmritaBot/AmritaBot)。

### 🚀 核心功能

- ✅ 开箱即用的多种模型协议支持（OpenAI / DeepSeek / Gemini 等）
- ✅ 可独立运行的聊天机器人
- ✅ 支持群聊与私聊双模式
- ✅ AT 触发与智能上下文管理
- ✅ 戳一戳消息交互支持
- ✅ 多模型热切换
- ✅ 多角色（预设）热切换
- ✅ 会话生命周期管理（超时自动清理 / 手动续聊）
- ✅ Function Calling 支持
  - ✅ 内置聊天不良内容检测（可配置熔断）
  - ✅ 基于 Cookie 检测的提示词防泄露
- ✅ 可选 MCP 支持

### 🧩 扩展体系

- 🔌 模块化模型预设架构（`config/models/`）
- 🧠 自定义提示词模板体系（`config/prompts/`）
- 📦 基于 nonebot-plugin-orm 的持久化存储
- 🧰 插件 API 全开放，易于开发拓展

### 🛠️ 高级功能

- 🤖 自动回复模式（概率性随机触发）
- ♻️ 消息撤回缓解机制
- 🚨 异常日志自动推送管理群
- ⏱️ 会话生命周期控制
- 📊 每日用量统计与频率限制（群 / 用户 / 全局）
- 🦺 提示词防泄露

## 📦 安装

提供两种安装方式：

- 方法一（推荐）：

  ```bash
  nb plugin install nonebot-plugin-suggarchat
  ```

- 方法二（手动安装）：

  ```bash
  pip install nonebot_plugin_suggarchat[openai]
  ```

  若使用方法二，还需在 `pyproject.toml` 中手动添加插件名：

  ```toml
  plugins = ["nonebot_plugin_suggarchat"]
  ```

---

## 🚀 快速部署

> 完整配置说明请查阅 [📘 使用文档](https://docs.suggar.top/project/suggarchat/)。

### 环境要求

- Python 3.10+
- NoneBot2 ≥ 2.4.0
- 一个 OneBot V11 协议端（如 NapCat / Lagrange / go-cqhttp 等）

### 安装

```bash
nb plugin install nonebot-plugin-suggarchat
```

或在 `pyproject.toml` 中手动添加并安装依赖：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_suggarchat"]
adapters = [
    { name = "OneBot V11", module_name = "nonebot.adapters.onebot.v11" },
]
```

```bash
pip install nonebot_plugin_suggarchat
```

### 首次启动

```bash
nb run
```

首次启动会自动创建插件数据目录，目录位置由
[nonebot-plugin-localstore](https://github.com/nonebot/plugin-localstore) 管理。
以 Linux 为例，默认位于：

```
~/.local/share/nonebot2/nonebot_plugin_suggarchat/
├── config.toml            # 插件主配置
├── models/                # 模型预设（*.json）
├── group_prompts/         # 群聊提示词模板（*.txt）
└── private_prompts/       # 私聊提示词模板（*.txt）
```

### 配置模型

1. 在 `models/` 目录下新建 `my_model.json`（可参考仓库内 `config/models/deepseek-v3.json`）：

   ```json
   {
     "model": "deepseek-chat",
     "name": "DS-V3",
     "base_url": "https://api.deepseek.com",
     "api_key": "sk-你的密钥",
     "config": {
       "top_k": 50,
       "top_p": 0.8,
       "temperature": 0.6,
       "stream": false,
       "multimodal": false
     }
   }
   ```

2. 编辑 `config.toml`，启用聊天并指定默认模型：

   ```toml
   enable = true
   preset = "my_model"

   [core.llm]
   max_tokens = 1000
   llm_timeout = 60
   ```

3. 保存后配置会自动热重载（无需重启）；也可以使用 `/presets`、`/set_preset` 在线切换模型。

> **提示**：`enable = false` 时机器人不响应任何聊天消息；如需完整 Agent
> 编排能力，请迁移至 [AmritaBot](https://github.com/AmritaBot/AmritaBot)。

---

## 🧭 快速参考

### 常用命令

直接发送消息即可与机器人聊天；发送 `/menu` 或 `/菜单` 可随时查看功能菜单。

```
/menu              — 查看聊天功能菜单
/prompt            — 自定义提示词
/choose_prompt     — 切换提示词模板
/presets           — 查看模型列表
/set_preset <名>   — 切换模型
/sessions          — 会话管理
/del_memory        — 清除记忆
/show-abstract     — 查看摘要
/insights          — 今日用量
/chatobj           — 会话状态
/mcp               — MCP 管理
/debug on|off|status — 调试开关
/chat on|off       — 启用/禁用聊天
/chat auto on|off  — 自动回复开关
/chat status       — 查看聊天状态
```

### 权限说明

| 等级 | 说明 | 命令示例 |
| --- | --- | --- |
| 超级用户 | 全局 `SUPERUSERS` | `/presets` `/set_preset` `/choose_prompt` `/sessions` `/debug` `/mcp` |
| 群管理 | 群主 / 管理员 / 超级用户 | `/prompt` `/chatobj` `/chat` |
| 普通用户 | 所有人 | `/menu` `/del_memory` `/show-abstract` `/insights` |

### 核心配置速览

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `enable` | 是否启用聊天能力 | `false` |
| `preset` | 默认使用的模型预设名称 | `"default"` |
| `function.enable_group_chat` | 是否启用群聊功能 | `true` |
| `function.enable_private_chat` | 是否启用私聊功能 | `true` |
| `function.poke_reply` | 是否响应戳一戳事件 | `true` |
| `session.session_control` | 是否启用会话超时自动清理 | `false` |
| `autoreply.enable` | 是否启用自动回复系统 | `false` |
| `core.llm.max_tokens` | 单次回复最大 Token 数 | `1000` |
| `core.llm.llm_timeout` | LLM 请求超时（秒） | `60` |
| `core.llm.memory_length_limit` | 记忆保留条数 | `50` |
| `usage_limit.enable_usage_limit` | 是否启用使用频率限制 | `false` |

## 💬 社区支持

如需帮助或参与讨论，欢迎加入我们的官方 QQ 群：`1006893368`
