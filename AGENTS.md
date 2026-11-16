# AGENTS.md

给 AI 助手（Cursor / Codex / Claude Code 等）的项目级约定。

## 禁止自动上传远端

未经用户在**当前对话中明确同意**，不得执行任何会把内容上传到远端的操作：

- `git push`（任何分支 / 任何参数，含 `--force`）
- `git push --tags`
- `gh release create` / `gh pr create` / `gh issue create`
- 向 GitHub 等远端平台上传 Release 附件或产物

允许：本地 `git add` / `git commit` / `git status` / `git diff` / `git log` / `git fetch` / `git pull`，
以及只读地查询远端状态（`git ls-remote`、`gh release list` 等）。

只有当用户当前轮明确要求"推送 / 发布 / 发到 GitHub"时才执行 push，并先告知目标仓库与分支。

## 其他约定

- 协议适配相关代码集中在 `batterytray/drivers/`，新增厂商协议前先跑 `verify_all.py`。
- 探测过程的临时输出（`asuskb.txt`、`hid_h.txt`、`mch5.txt`、`pprovider.txt`）不要提交。
