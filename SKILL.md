---
name: daily-paper
description: Portable daily paper curation, verification, and bookshelf publishing skill. Use when generating a daily paper digest, updating user research preferences or reading feedback, validating a daily issue JSON, or rendering/publishing the daily paper bookshelf across any agent (Antigravity, Codex, Claude Code, Cursor, or CI).
---

# Daily Paper · 跨 Agent 每日论文推荐与书架系统

本仓库本身就是一个可移植的 **Repo-as-a-Skill**：所有主题偏好、关注基准、阅读反馈、编辑规则、数据契约、采集/校验/渲染脚本和历史归档都在同一个 Git 仓库中。任何支持 `SKILL.md` 的 Agent 或定时任务只需挂载本仓库，即可按同一套标准运行。

## 核心原则（必读）

1. **宽进严标、导读优先（高召回新作追踪）**：
   - 不要因为新论文尚未沉淀或“看起来不够突破”就激进拒稿。近期贴题新作应尽量收录，通过**1–2 句白话导读**和**透明标签（`tags`）**让读者一眼决定是否点开深读，把最终取舍权交给读者。
   - 仅排除明显跑题的内容（如金融 RSI、无代码参与的纯文生图/文生视频、毫无技术细节的纯营销帖）。
2. **两级阅读深度（`reading_tier`）**：
   - `deep`（深度精读）：核心主线高贴题、方法扎实、开源环境/代码/数据、真实在线评测、或高热老作/获奖作。写足方法机制、实验条件与局限对比。
   - `scan`（新作速览）：其他贴题近期新作。保持完整结构化字段，重点把 `intro`（白话导读）和 `tags` 写清，帮助读者 5 秒判断值不值得细看。
3. **一手证据、绝不脑补**：
   - 标题、作者、日期、方法、实验数字、热度必须核验一手来源（arXiv / OpenReview / 论文集 / 官方项目页 / OpenAlex / HF Papers / GitHub）。查不到就明说，缺项不算 0。
4. **偏好配置化与反馈闭环**：
   - 每次运行前必须读取 `profile/topics.json`、`profile/watchlist.json` 和 `profile/feedback.jsonl`；永远以 `profile/` 中的最新配置为准，不要凭记忆假设主题列表。

## 标准执行流程（6 步）

> 所有命令均以本仓库根目录为工作目录，且零第三方 Python 依赖（Python 3.9+ 标准库即可运行）。

### Step 1：确定北京时间日期并加载偏好与历史

- 显式确定目标日期 `YYYY-MM-DD`（北京时间 `Asia/Shanghai`，不要依赖机器默认时区）。
- 读取：
  - `profile/topics.json`（主题、Tier 优先级、锚点、检索词、排除边界）
  - `profile/watchlist.json`（重点 Benchmark、已有论文库锚点、工程信号标签）
  - `profile/feedback.jsonl`（历史用户反馈，用于微调排序与 `deep`/`scan` 归类）
  - `docs/editorial-policy.md` 与 `docs/agent-contract.md`

### Step 2：运行确定性候选采集脚本

```bash
python3 scripts/fetch_candidates.py --date YYYY-MM-DD --days 14 --output /tmp/daily-paper-candidates-YYYY-MM-DD.json
```

脚本会自动：
- 扫描 `issues/*.json` 建立历期去重索引；
- 抓取 arXiv 最新论文 + Hugging Face Daily Papers；
- 尝试补齐 OpenAlex 引用数与官方 GitHub 仓库 Star 数；
- 输出按主题初步召回的候选列表（含 `already_archived` 标记）。

### Step 3：补充检索与一手核验

对脚本未覆盖到的来源进行补充检索（并行覆盖四条轨道）：
- **近期新作（`fresh`，优先 7 天，可放宽至 14 天）**：补查 OpenReview、技术报告、实验室博客，特别是脚本召回偏少的栏目（如多模态编程五个子方向、游戏智能体、Personal Agent）。
- **高热老作（`popular_backlist`，>14 天未收录）**：每期跨主题选 1–3 篇仍具高参考价值的工作，附可点击的 `backlist_evidence`。
- **顶会获奖（`award`）与专题补读（`supplement`）**：独立于老作名额；Oral / Spotlight / Highlights 不等于获奖。

核验每篇入选论文的一手原文（至少读清摘要、方法、实验主表/条件与局限），切勿仅凭标题或社区转述猜数字。

### Step 4：生成当期日报 JSON

将当期结果写入 `issues/YYYY-MM-DD.json`，严格遵循：
- `schema/issue.schema.json`（`schema_version: "1.1"`）
- `docs/editorial-policy.md`（写作规范与热度 v1 口径）
- `docs/agent-contract.md`（字段映射、去重与幂等要求）

注意：
- `sections` 顺序与主题名必须与 `profile/topics.json` 一致；每天全部栏目都查，不轮换。
- 跨栏命中的论文只在一个主栏目详解，其余相关栏目通过 `secondary_topics` 标注或交叉提及。
- 每篇论文标注 `reading_tier`（`deep` 或 `scan`）与客观 `tags`（如 `open-env`、`open-code`、`online-rl`、`verifiable-reward`、`real-eval`、`offline-only`、`no-code-yet`）。
- 不输出总热度分，只记录原始已核验 `heat.signals`（或 `heat.unavailable`），呈现层自动计算 Heat v1 分数与覆盖度。

### Step 5：确定性校验（必须通过）

```bash
python3 scripts/validate_issue.py issues/YYYY-MM-DD.json
```

如果校验报错（Schema 违规、日期/lane 冲突、首推 ID 不存在、未说明的跨期重荐、多模态缺 `directions` 等），必须修复后重新运行直到退出码为 `0`。

### Step 6：渲染静态书架网页并发布

```bash
python3 scripts/render_bookshelf.py --issues-dir issues --output dist/index.html
```

然后按目标环境选择发布适配器（详见 `publishers/README.md`）：
- **ZhiWei 静态托管（推荐免登录）**：读取 `dist/index.html` 调用 `publish_zhiwei_static_report`（可固定 `publicPath` 如 `daily-paper/index.html` 实现每日更新同一主页 URL）。
- **GitHub Pages**：提交 `issues/YYYY-MM-DD.json` 推送至 `main`，由 GitHub Actions 自动渲染并部署。
- **旧书架兼容导出**：运行 `python3 scripts/render_bookshelf.py --export-legacy issues/YYYY-MM-DD.json` 生成旧格式 JSON。

发布后执行回读校验，确认日期、首推、栏目顺序、篇数和关键链接无误。

## 用户维护偏好与反馈的快捷方式

- **调整主题/权重/关键词**：直接编辑 `profile/topics.json` 和 `profile/watchlist.json`。
- **记录阅读反馈**：向 `profile/feedback.jsonl` 追加一行 JSON，例如：
  ```json
  {"date": "2026-11-26", "paper_id": "arxiv:2610.12611", "title": "SoftwareGym", "verdict": "liked", "note": "可扩展软件环境与可验证任务非常贴合"}
  ```
  `verdict` 可选：`liked` / `deep_read` / `skipped` / `off_topic`。
