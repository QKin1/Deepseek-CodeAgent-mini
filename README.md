# DeepSeek Code Agent

基于单 Agent Loop 的 Windows 桌面代码生成器。用户选择架构文档、PlantUML 架构视图和输出目录；应用先在本机生成 `architecture.json` 与 `architecture_review.md`，再通过 DeepSeek 官方 Responses API 根据架构生成项目代码。

## 功能

- PySide6 桌面 GUI：配置 API Key、测试 API、选择输入文件和输出目录、启动或取消任务。
- 模型：`deepseek-v4-pro`，通过官方 API 调用，不使用本地模型权重。
- 输入：`.md` / `.markdown`；提取 Markdown 需求 ID、组件、PlantUML fenced block、交付路径和开放问题。
- 输出：架构 JSON、架构审查报告，以及 Agent 生成的源码、依赖声明、README 和测试用例。
- 安全：文件工具限制在选定输出目录；禁止 Shell；路径和工具参数本地校验；完成任务前检查基本交付物。
- Windows API Key 存储：可选使用当前 Windows 用户 DPAPI 加密到 `%LOCALAPPDATA%`。

## 本机开发

需要 Windows、Python 3.11+。在项目目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果执行环境的 Python 没有 `ensurepip`，使用已安装的 Python/pip 环境创建虚拟环境，或在隔离的开发环境中安装 `requirements.txt`。

启动 GUI：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -m code_agent.main
```

运行测试：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:QT_QPA_PLATFORM = 'offscreen'
python -m pytest --basetemp '.pytest-tmp' -q
```

默认测试使用 Mock Provider，不需要 API Key。真实 API 连通性测试需在 GUI 中输入自己的 DeepSeek API Key。API Key 不应写进代码、命令历史、测试 fixture 或日志。

## 打包 Windows EXE

PyInstaller 会把 Python 解释器和运行依赖一起打进 EXE，目标机器无需另装 Python。为避免开发机全局 Qt/Python 包污染 onefile 产物，构建脚本使用两个隔离依赖目录。首次构建前执行：

```powershell
New-Item -ItemType Directory -Force .packages, .qt-packages | Out-Null
python -m pip install --target .packages --no-warn-script-location "httpx>=0.27,<1" "jsonschema>=4.22,<5" "PyInstaller>=6.11,<7"
python -m pip install --target .qt-packages --no-warn-script-location "PySide6-Essentials==6.8.3"
.\build.ps1
```

发布文件位于 `dist\CodeAgent.exe`。Qt 6.8.3 是目前已完成 Windows onefile 启动验证的固定版本。构建后应在目标 Windows 环境验证启动、输入/输出路径和 Qt 插件加载；升级 Qt 版本时必须重新做同样的 EXE 冒烟验证。

## 当前限制

- 当前没有任意命令执行、MCP、多 Agent 或自动部署能力。
- PlantUML 以结构提取和原文保留为主，不保证完整语法/语义验证。
- Agent 生成的代码不会自动运行；应用只能进行有限的本地文件和 JSON 检查。
- API 服务需要网络和有效 API Key；架构内容会发送给 DeepSeek 官方 API。

## 主要目录

```text
src/code_agent/       应用、GUI、Agent、API、解析器和安全工具
tests/                单元、契约、集成和 GUI 冒烟测试
schemas/              结构化架构 JSON Schema
Architecture_*.md     当前架构输入样例
```
