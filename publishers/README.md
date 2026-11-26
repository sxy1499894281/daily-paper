# 发布适配器说明（`publishers/`）

本仓库将**内容生产（`issues/YYYY-MM-DD.json`）**与**网页发布**完全解耦。所有历史日报均归档在私有仓库的 `issues/` 目录下，可通过 `scripts/render_bookshelf.py` 一键渲染成独立单文件 HTML 书架页 `dist/index.html`，再按需发布到任意目标。

## 方案 A：ZhiWei 静态页托管（Antigravity 环境最省事，免 ChatGPT 登录）

1. 生成静态单文件 HTML：
   ```bash
   python3 scripts/render_bookshelf.py --issues-dir issues --output dist/index.html
   ```
2. 在 Antigravity 中调用 `zhiwei` MCP 工具 `publish_zhiwei_static_report`：
   - `title`: `"Daily Paper · 每日论文书架"`
   - `reportKind`: `"general"`
   - `publicPath`: `"daily-paper/bookshelf.html"`（固定路径，每天覆盖更新同一个 URL，所有历史日期都在页面内可切换）
   - `html`: `dist/index.html` 的完整内容

## 方案 B：GitHub Pages（纯公网托管，自动部署）

仓库已预置 `.github/workflows/deploy-pages.yml`：
1. 如需公开访问，可将仓库（或单独建一个公开展示仓库）开启 **Settings → Pages → Source: GitHub Actions**；
2. 每次提交新的 `issues/YYYY-MM-DD.json` 到 `main`，GitHub Actions 会自动校验并渲染部署最新书架主页。

## 方案 C：兼容原 ChatGPT 书架格式

如果仍需向旧书架结构同步，可运行：

```bash
python3 scripts/render_bookshelf.py --export-legacy issues/YYYY-MM-DD.json --output /tmp/legacy-issue.json
```

输出严格符合 `docs/agent-contract.md` 中定义的旧书架 JSON 映射格式。
