# 个人偏好配置说明（`profile/`）

本目录是整个日报系统的**个人喜好单一事实源**，与具体 Agent、模型和发布平台完全解耦。修改本目录并推送到 Git 后，所有接入本仓库的 Agent 都会立即按最新偏好工作。

## 文件职责

- [topics.json](topics.json)：主题清单、优先级分级（`tier1` 核心主线 vs `tier2` 扩展追踪）、高召回追踪原则、各主题锚点论文、arXiv 检索词、硬排除边界与标签体系。
- [watchlist.json](watchlist.json)：你重点关注的 Benchmark、已有精读论文锚点库、arXiv 分类和工程价值标签字典。
- [feedback.jsonl](feedback.jsonl)：你的个人阅读反馈日志（每行一条 JSON）。Agent 每次选稿和决定 `deep` / `scan` 档位前都会先读取它。

## 如何记录阅读反馈

向 `profile/feedback.jsonl` 追加一行 JSON 即可：

```json
{"date": "2026-11-26", "paper_id": "arxiv:2610.12611", "title": "SoftwareGym", "verdict": "liked", "note": "自动合成可验证软件环境，非常贴合我关心的方向"}
{"date": "2026-11-26", "paper_id": "arxiv:2611.00001", "title": "Some Wrapper Paper", "verdict": "skipped", "note": "纯 prompt 拼接，无真实环境实验"}
```

建议的 `verdict` 取值：
- `liked`：很对胃口，同类方向以后优先给 `deep`
- `deep_read`：已精读并加入论文库，可作为后续横向对比锚点
- `skipped`：看导读后无兴趣（正常现象，仅在同类多次跳过且注明原因时调低权重）
- `off_topic`：明显跑题，应补充到对应主题的 `hard_exclusions`
