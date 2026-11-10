# Study Planner 架构说明

## 1. 项目目标

实现一个小型命令行学习计划管理器 Study Planner。用户可以创建学习任务、列出任务、标记任务完成和删除任务。任务保存在 JSON 文件中。

This acceptance sample uses Python 3.11 or later and the Python standard library only. It must work offline after installation.

## 2. Requirements

- **FR-1**：用户可以创建学习任务。每个任务必须有非空标题，可选包含备注。
- **FR-2**：用户可以列出任务、标记任务完成并删除任务。
- **FR-3**：任务列表在程序退出后保留，JSON 文件不存在时按空列表处理。
- **NFR-1**：核心逻辑可在不访问网络、不安装第三方运行依赖的条件下使用。
- **ASR-1**：命令行交互、业务规则和 JSON 文件存储分为独立模块。
- **SEC-1**：程序只读写用户指定的 Study Planner 数据文件，不扫描其他目录。

## 3. Requirements Traceability Matrix

| Requirement | Design area | Verification |
|---|---|---|
| FR-1 | PlannerServiceComponent | Create task validation tests |
| FR-2 | CliComponent and PlannerServiceComponent | List, complete, delete tests |
| FR-3 | JsonRepositoryComponent | Save and reload tests |
| NFR-1 | All application components | Standard-library-only dependency review |
| ASR-1 | Component boundaries | Architecture and module review |
| SEC-1 | JsonRepositoryComponent | Tests use a temporary data file |

## 4. Architecture Overview

The application consists of the following components:

- **CliComponent** parses user commands, calls the service, and prints results.
- **PlannerServiceComponent** applies task rules and coordinates repository operations.
- **JsonRepositoryComponent** reads and writes tasks through a file abstraction.
- **TaskModelComponent** represents a task and validates its basic fields.

The CLI does not directly manipulate JSON. The service does not print to the terminal. The repository does not decide whether a task title is valid.

## 5. Data Model

Each task contains:

- `id`: stable unique string identifier.
- `title`: non-empty user-visible title.
- `notes`: optional string, empty by default.
- `completed`: boolean, false by default.
- `created_at`: ISO 8601 timestamp.

The repository serializes the task list as UTF-8 JSON. Writes should use a temporary file and atomic replacement where supported.

## 6. Error Handling

- Empty titles are rejected with a useful message.
- Completing or deleting an unknown ID returns a not-found result without corrupting stored data.
- Invalid JSON is reported clearly; the program must not silently overwrite the invalid file with an empty list.
- File permission errors are surfaced to the caller.

## 7. Expected Deliverables

- Python source code under `src/`.
- `requirements.txt` documenting that there are no third-party runtime dependencies.
- `README.md` with setup, commands, storage behavior, and test instructions.
- Tests under `tests/` for create, list, complete, delete, persistence, invalid title, and unknown ID.

## 8. Scope

This is a local single-user learning project. It does not require a database server, web framework, authentication, network calls, Docker, or a graphical interface.

