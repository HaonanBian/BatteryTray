# AGENTS.md

给 AI 助手（Cursor / Codex / Claude Code 等）的项目级约定。

## 分支约定

- `main` —— 只放**已经改好、可以直接用**的更新。
- `task` —— 其它所有工作（半成品、试验、还没验证的改动）都放这里。

动手改代码之前先看清楚自己在哪个分支上：

- 修 bug、加功能、改界面这类**会变成正式更新**的改动，提交到 `main`。
- 其它一律先开一个 `task` 分支再动手。

不要把半成品直接推到 `main`。一个提交进 `main` 的东西应该是能跑、
测试过了的。

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
