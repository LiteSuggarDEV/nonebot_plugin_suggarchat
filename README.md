<div align="center">
  <a href="https://github.com/JohnRichard4096/nonebot_plugin_suggarchat/">
    <img src="https://github.com/user-attachments/assets/b5162036-5b17-4cf4-b0cb-8ec842a71bc6" width="200" alt="SuggarChat Logo">
  </a>
  <h1>SuggarChat</h1>
  <h3>高扩展性的大模型聊天框架</h3>

  <p>
    <a href="https://pypi.org/project/nonebot-plugin-suggarchat/">
      <img src="https://img.shields.io/pypi/v/nonebot-plugin-suggarchat?color=blue&style=flat-square" alt="PyPI Version">
    </a>
    <a href="https://www.python.org/">
      <img src="https://img.shields.io/badge/python-3.9+-blue?logo=python&style=flat-square" alt="Python Version">
    </a>
    <a href="https://nonebot.dev/">
      <img src="https://img.shields.io/badge/nonebot2-2.0.0rc4+-blue?style=flat-square" alt="NoneBot Version">
    </a>
    <a href="LICENSE">
      <img src="https://img.shields.io/github/license/JohnRichard4096/nonebot_plugin_suggarchat?style=flat-square" alt="License">
    </a>
    <a href="https://qm.qq.com/q/PFcfb4296m">
      <img src="https://img.shields.io/badge/QQ%E7%BE%A4-1002495699-blue?style=flat-square" alt="QQ Group">
    </a>
  </p>
</div>

## ✨ 特性一览

### 🚀 核心功能

- ✅ 开箱即用的多种协议支持（OpenAI / DeepSeek / Gemini 等）
- ✅ 可独立运行的聊天机器人
- ✅ 支持群聊与私聊双模式
- ✅ AT 触发与智能上下文管理
- ✅ 戳一戳消息交互支持
- ✅ 多模型热切换
- ✅ 多角色热切换
- ✅ 会话生命周期管理
- ✅ 聊天模型切换
- ✅ 多模态模型支持
- ✅ Function Calling支持
  - ✅ 内置聊天不良内容检测
  - ✅ 基于Cookie检测的提示词防泄露

### 🧩 扩展体系

- 🔌 模块化协议适配器架构
- 🧠 自定义消息解析引擎
- 📦 自定义依赖扩展式Matcher接口
- 🧰 插件 API 全开放，易于开发拓展

### 🛠️ 高级功能

- 🤖 自动回复模式（概率性自动回复）
- ♻️ 消息撤回缓解机制
- 🚨 异常日志自动推送管理群
- ⏱️ 会话生命周期控制
- 🔐 Token 智能管理策略
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

## 🧭 快速开始

请查阅我们的 [📘 使用文档](https://docs.suggar.top/project/suggarchat/) 来了解如何快速部署和配置。

## 💬 社区支持

如需帮助或参与讨论，欢迎加入我们的官方 QQ 群：[812849068](https://qm.qq.com/q/VdE1OkBNaU)
