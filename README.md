# Daily Paper · 每日论文推荐与跨 Agent Skill 仓库

- **在线书架主页（GitHub Pages）**：https://sxy1499894281.github.io/daily-paper/
- **每日更新流程**：提交 `issues/YYYY-MM-DD.json` 推送至 `main` 后，GitHub Actions 自动校验并更新在线书架，保留全部历史期号。

一个**可迁移到任意 Agent（Antigravity / Codex / Claude Code / Cursor / GitHub Actions）**的个人每日论文推荐系统。你的研究偏好、锚点论文、阅读反馈、历史归档和确定性工具脚本全部沉淀在这个 Git 仓库里，一次维护，处处生效。

## 核心特点

- **Repo 即 Skill**：根目录直接提供标准 [SKILL.md](SKILL.md)，挂载到任意支持 Skill 的 Agent 即可按统一标准产出每日论文日报。
- **宽进严标、导读优先**：不激进漏杀刚发表的新作；通过 **Tier 1 核心主线 / Tier 2 雷达追踪** 与 **`deep` 精读 / `scan` 速览** 两级深度，加上透明工程标签（`open-env`、`online-rl`、`real-eval`、`offline-only` 等），让你 1 分钟扫完导读、秒判值不值得细看。
- **零依赖确定性工具链**：`scripts/` 仅使用 Python 3.9+ 标准库，把 arXiv / Hugging Face Daily Papers 候选拉取、OpenAlex / GitHub 热度补齐、Schema 与跨期去重校验、单文件 HTML 书架渲染全部脚本化。
- **归档与平台解耦**：每日结果沉淀在 `issues/YYYY-MM-DD.json`，天然充当跨平台去重数据库，可一键发布到 ZhiWei 静态页、GitHub Pages 或兼容旧书架。

## 目录结构

| 路径 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | 跨 Agent 通用 Skill 入口与 6 步工作流 |
| [profile/topics.json](profile/topics.json) | 个人主题、Tier 1/2 分级、高召回策略、检索词与锚点 |
| [profile/watchlist.json](profile/watchlist.json) | 关注 Benchmark、已有论文库锚点与工程价值标签 |
| [profile/feedback.jsonl](profile/feedback.jsonl) | 个人阅读反馈日志（持续校准推荐权重） |
| [docs/editorial-policy.md](docs/editorial-policy.md) | 编辑策略 v1.1：高召回追踪、证据要求与热度 v1 公式 |
| [docs/agent-contract.md](docs/agent-contract.md) | Agent 接入契约 v1.1：流程、校验、幂等发布与旧书架适配 |
| [schema/issue.schema.json](schema/issue.schema.json) | 日报 JSON Schema v1.1（向下兼容 v1.0） |
| [scripts/fetch_candidates.py](scripts/fetch_candidates.py) | 抓取 arXiv + HF Daily Papers 候选、补齐热度并自动标记已归档 |
| [scripts/validate_issue.py](scripts/validate_issue.py) | 校验 Schema、栏目一致性、跨期去重、日期与 lane 规则 |
| [scripts/render_bookshelf.py](scripts/render_bookshelf.py) | 将 `issues/*.json` 渲染为可搜索/可筛选的单文件 HTML 书架 |
| [publishers/README.md](publishers/README.md) | ZhiWei 静态页、GitHub Pages 与旧书架发布指南 |
| `issues/` | 历期真实日报 JSON 归档（`YYYY-MM-DD.json`） |

## 快速迁移到任意 Agent

```bash
# 1. 克隆本私有仓库
git clone https://github.com/sxy1499894281/daily-paper.git

# 2. 按需软链到对应 Agent 的 skills 目录（以 Antigravity / Claude Code 为例）
ln -s /path/to/daily-paper ~/.gemini/config/skills/daily-paper
# 或 ~/.claude/skills/daily-paper
```

## 本地验证最小命令

```bash
# 校验示例日报
python3 scripts/validate_issue.py examples/issue.json

# 用示例日报预览生成的书架 HTML
python3 scripts/render_bookshelf.py --issue examples/issue.json --output dist/preview.html

# 抓取最近 7 天真实候选论文（用于生成当期日报）
python3 scripts/fetch_candidates.py --days 7 --output /tmp/candidates.json
```
