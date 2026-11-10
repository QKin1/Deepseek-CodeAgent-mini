# Study Planner 冲突检测样例

## Purpose

This deliberately inconsistent fixture verifies that preprocessing reports contradictions instead of silently choosing one statement.

The architecture documentation claims that it has 3 UML diagrams.

## Requirements

- **FR-1**：用户可以创建任务。
- **FR-2**：用户可以标记任务完成。
- **FR-3**：任务可以保存到本地 JSON 文件。

## Requirements Traceability Matrix

| Requirement | Area | Verification |
|---|---|---|
| FR-1 | PlannerServiceComponent | Create task test |
| FR-3 | JsonRepositoryComponent | Persistence test |

FR-2 is intentionally absent from this matrix.

## Architecture Overview

- **PlannerServiceComponent** handles task rules.
- **JsonRepositoryComponent** persists task data.

The deployment section names `sql/tasks_ddl.sql` as the database script. A later delivery section names `sql/task_ddl.sql` as the database script.

## Open Questions

- Should task completion be persisted immediately or only when the application exits?

## Expected Deliverables

- README.md
- requirements.txt
- project source code
- project tests

