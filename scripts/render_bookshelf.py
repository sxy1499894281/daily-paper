#!/usr/bin/env python3
"""Render Daily Paper archived JSON issues into a self-contained single-file HTML bookshelf,
or export an issue to the legacy bookshelf JSON format.

Zero external dependencies (Python 3.9+ stdlib only).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

LANE_PREFIX = {
    "popular_backlist": "补读·高热老作",
    "award": "补读·顶会获奖",
    "supplement": "补读·专题补读",
}


def compute_heat_v1(heat: dict[str, Any]) -> tuple[int | None, int]:
    signals = heat.get("signals")
    if not isinstance(signals, list) or not signals:
        return None, 0
    citations: int | None = None
    votes: int | None = None
    comments: int | None = None
    stars: int | None = None
    for s in signals:
        kind = s.get("kind")
        cnt = s.get("count")
        if not isinstance(cnt, int) or isinstance(cnt, bool) or cnt < 0:
            continue
        if kind == "citations":
            citations = cnt if citations is None else max(citations, cnt)
        elif kind == "votes":
            votes = cnt if votes is None else max(votes, cnt)
        elif kind == "comments":
            comments = cnt if comments is None else max(comments, cnt)
        elif kind == "stars":
            stars = cnt if stars is None else max(stars, cnt)

    total = 0.0
    coverage = 0
    if citations is not None:
        total += citations * 3
        coverage += 1
    if votes is not None or comments is not None:
        total += max(votes or 0, (comments or 0) * 2)
        coverage += 1
    if stars is not None:
        total += stars * 0.1
        coverage += 1
    if coverage == 0:
        return None, 0
    return int(round(total)), coverage


def format_legacy_heat(paper: dict[str, Any], issue_date: str) -> str:
    heat = paper.get("heat") or {}
    signals = heat.get("signals") or []
    parts: list[str] = []
    kind_meta = {
        "citations": ("学术引用", "次"),
        "votes": ("社区讨论", "票"),
        "comments": ("社区讨论", "评"),
        "stars": ("仓库关注", "星"),
    }
    for s in signals:
        label, unit = kind_meta.get(s.get("kind", ""), ("其他", ""))
        approx = "约 " if s.get("approximate") else ""
        parts.append(
            f"{label} · {s['source']} {approx}{s['count']} {unit}（{s['observed_on']}） | {s['url']}"
        )
    if parts:
        line = "热度：" + "；".join(parts)
    else:
        line = f"热度：暂无可核验数据（{issue_date}）"
    award = paper.get("award")
    if isinstance(award, dict):
        line += (
            f"\n官方奖项：{award['venue']} {award['year']} {award['name']}（不计入热度） | {award['url']}"
        )
    return line


def to_legacy_issue(issue: dict[str, Any]) -> dict[str, Any]:
    issue_date = issue["date"]
    lead_id = issue["lead"]["paper_id"]
    lead_title = lead_id
    lead_url = ""
    for sec in issue.get("sections", []):
        for p in sec.get("papers", []):
            if p["id"] == lead_id:
                lead_title = p["title"]
                lead_url = p["url"]
                break

    lead_text = f"{lead_title} — {issue['lead']['reason']}"
    if issue["lead"].get("section_ref"):
        lead_text += f"（{issue['lead']['section_ref']}）"

    legacy_sections = []
    for sec in issue.get("sections", []):
        legacy_papers = []
        for p in sec.get("papers", []):
            blocks: list[str] = []
            if p.get("directions"):
                blocks.append("【方向：" + " / ".join(p["directions"]) + "】")
            intro_prefix = ""
            if p.get("lane") in LANE_PREFIX:
                intro_prefix = f"【{LANE_PREFIX[p['lane']]}】"
            blocks.append(f"导读：{intro_prefix}{p['intro']}")
            blocks.append(f"方法论：{p['method']}")
            blocks.append(f"实验结果：{p['results']}")
            blocks.append(format_legacy_heat(p, issue_date))
            legacy_papers.append(
                {
                    "title": p["title"],
                    "date": p["published_on"],
                    "url": p["url"],
                    "abstract": p["abstract_zh"],
                    "explain": "\n\n".join(blocks),
                    "limit": p["limitation"],
                }
            )
        legacy_sections.append(
            {
                "topic": sec["topic"],
                "note": sec.get("note", ""),
                "papers": legacy_papers,
            }
        )
    return {
        "date": issue_date,
        "lead": lead_text,
        "lead_url": lead_url,
        "sections": legacy_sections,
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Daily Paper · 每日论文书架</title>
  <style>
    :root {
      --bg: #f7f6f2;
      --surface: #ffffff;
      --surface-soft: #f2f0ea;
      --text: #1c1917;
      --muted: #57534e;
      --border: #e7e5e4;
      --accent: #2563eb;
      --accent-soft: #eff6ff;
      --tier1: #0f766e;
      --tier1-bg: #f0fdfa;
      --tier2: #6d28d9;
      --tier2-bg: #f5f3ff;
      --deep: #b45309;
      --deep-bg: #fffbeb;
      --scan: #0369a1;
      --scan-bg: #f0f9ff;
      --warn: #b91c1c;
      --warn-bg: #fef2f2;
      --shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    }
    [data-theme="dark"] {
      --bg: #111318;
      --surface: #181c23;
      --surface-soft: #202631;
      --text: #f3f4f6;
      --muted: #9ca3af;
      --border: #2a3140;
      --accent: #60a5fa;
      --accent-soft: #172554;
      --tier1: #2dd4bf;
      --tier1-bg: #134e4a;
      --tier2: #c4b5fd;
      --tier2-bg: #3b0764;
      --deep: #fbbf24;
      --deep-bg: #451a03;
      --scan: #38bdf8;
      --scan-bg: #0c4a6e;
      --warn: #fca5a5;
      --warn-bg: #450a0a;
      --shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.65;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .container { max-width: 1100px; margin: 0 auto; padding: 20px 18px 64px; }
    header {
      display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
      gap: 12px; padding-bottom: 16px; border-bottom: 1px solid var(--border);
    }
    .brand h1 { margin: 0; font-size: 1.55rem; letter-spacing: -0.02em; }
    .brand p { margin: 2px 0 0; color: var(--muted); font-size: 0.9rem; }
    .controls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
    select, button, input[type="search"] {
      font: inherit; color: var(--text); background: var(--surface);
      border: 1px solid var(--border); border-radius: 8px; padding: 6px 11px;
    }
    button { cursor: pointer; }
    button:hover { border-color: var(--accent); }
    .lead-card {
      margin-top: 18px; padding: 16px 18px; border-radius: 12px;
      background: var(--surface); border: 1px solid var(--border);
      border-left: 4px solid var(--accent); box-shadow: var(--shadow);
    }
    .lead-label {
      font-size: 0.78rem; font-weight: 700; text-transform: uppercase;
      color: var(--accent); letter-spacing: 0.04em;
    }
    .lead-title { margin: 4px 0 6px; font-size: 1.12rem; font-weight: 700; }
    .lead-reason { margin: 0; color: var(--muted); font-size: 0.95rem; }
    .toolbar {
      margin-top: 16px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
      justify-content: space-between;
    }
    .pills { display: flex; flex-wrap: wrap; gap: 6px; }
    .pill {
      font-size: 0.84rem; padding: 4px 10px; border-radius: 999px;
      border: 1px solid var(--border); background: var(--surface); color: var(--muted);
    }
    .pill.active {
      background: var(--accent); color: #fff; border-color: var(--accent);
    }
    .search-box { min-width: 220px; flex: 1; max-width: 320px; }
    nav.topics {
      position: sticky; top: 0; z-index: 10; background: var(--bg);
      padding: 10px 0; margin-top: 12px; border-bottom: 1px solid var(--border);
      display: flex; flex-wrap: nowrap; overflow-x: auto; gap: 8px;
    }
    nav.topics a {
      white-space: nowrap; font-size: 0.86rem; padding: 5px 11px; border-radius: 8px;
      background: var(--surface); border: 1px solid var(--border); color: var(--text);
    }
    nav.topics a .cnt { color: var(--muted); font-size: 0.78rem; margin-left: 4px; }
    section.topic-block { margin-top: 28px; scroll-margin-top: 66px; }
    .topic-header {
      display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
      margin-bottom: 10px;
    }
    .topic-header h2 { margin: 0; font-size: 1.25rem; }
    .badge {
      display: inline-flex; align-items: center; font-size: 0.75rem; font-weight: 600;
      padding: 2px 8px; border-radius: 999px; border: 1px solid transparent;
    }
    .badge.tier1 { color: var(--tier1); background: var(--tier1-bg); }
    .badge.tier2 { color: var(--tier2); background: var(--tier2-bg); }
    .badge.deep { color: var(--deep); background: var(--deep-bg); }
    .badge.scan { color: var(--scan); background: var(--scan-bg); }
    .badge.lane { color: var(--accent); background: var(--accent-soft); }
    .badge.warn { color: var(--warn); background: var(--warn-bg); }
    .badge.tag { color: var(--muted); background: var(--surface-soft); border-color: var(--border); font-weight: 500; }
    .topic-note {
      margin: 0 0 12px; padding: 8px 12px; border-radius: 8px;
      background: var(--surface-soft); color: var(--muted); font-size: 0.88rem;
    }
    .paper-card {
      background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
      padding: 15px 17px; margin-bottom: 12px; box-shadow: var(--shadow);
    }
    .paper-card.is-deep { border-left: 3px solid var(--deep); }
    .paper-card.is-scan { border-left: 3px solid var(--scan); }
    .paper-top {
      display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between;
      gap: 8px;
    }
    .paper-title { margin: 0; font-size: 1.03rem; font-weight: 700; line-height: 1.4; }
    .paper-meta {
      margin-top: 6px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
      font-size: 0.82rem; color: var(--muted);
    }
    .paper-intro {
      margin: 10px 0 8px; font-size: 0.96rem; color: var(--text);
    }
    .heat-pill {
      white-space: nowrap; font-size: 0.8rem; padding: 3px 9px; border-radius: 999px;
      background: var(--surface-soft); border: 1px solid var(--border); color: var(--muted);
    }
    details.paper-details { margin-top: 8px; }
    details.paper-details summary {
      cursor: pointer; font-size: 0.86rem; color: var(--accent); font-weight: 600;
      user-select: none;
    }
    .detail-grid {
      margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border);
      display: grid; gap: 10px; font-size: 0.92rem;
    }
    .detail-block h4 { margin: 0 0 3px; font-size: 0.84rem; color: var(--muted); }
    .detail-block p { margin: 0; white-space: pre-wrap; }
    .empty-msg { color: var(--muted); font-size: 0.92rem; padding: 12px 0; }
    footer {
      margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--border);
      color: var(--muted); font-size: 0.82rem; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <h1>Daily Paper · 每日论文书架</h1>
        <p id="subtitle">宽进严标 · 导读优先 · 跨 Agent 归档</p>
      </div>
      <div class="controls">
        <select id="dateSelect" aria-label="选择期号"></select>
        <button id="toggleExpandBtn" type="button">展开全部详情</button>
        <button id="themeBtn" type="button">切换深色</button>
      </div>
    </header>

    <div id="leadContainer"></div>

    <div class="toolbar">
      <div class="pills" id="filterPills">
        <button class="pill active" data-filter="all">全部</button>
        <button class="pill" data-filter="deep">深度精读</button>
        <button class="pill" data-filter="scan">新作速览</button>
        <button class="pill" data-filter="tier1">仅 Tier 1 核心</button>
        <button class="pill" data-filter="open">开源代码/环境</button>
        <button class="pill" data-filter="online-rl">在线 RL</button>
        <button class="pill" data-filter="backlist">老作/获奖</button>
      </div>
      <input class="search-box" id="searchInput" type="search" placeholder="搜索标题、导读、标签、方法..." />
    </div>

    <nav class="topics" id="topicNav"></nav>
    <main id="content"></main>

    <footer>
      <span id="statsFooter"></span>
      <span>Powered by Daily Paper Repo-as-a-Skill (Schema v1.1 · Heat v1)</span>
    </footer>
  </div>

  <script id="issues-data" type="application/json">__ISSUES_JSON__</script>
  <script>
    const ISSUES = JSON.parse(document.getElementById("issues-data").textContent);
    const LANE_LABELS = {
      fresh: "近期新作",
      popular_backlist: "高热老作",
      award: "顶会获奖",
      supplement: "专题补读",
    };

    let currentIdx = 0;
    let activeFilter = "all";
    let searchQuery = "";
    let allExpanded = false;

    const dateSelect = document.getElementById("dateSelect");
    const themeBtn = document.getElementById("themeBtn");
    const toggleExpandBtn = document.getElementById("toggleExpandBtn");
    const searchInput = document.getElementById("searchInput");

    function esc(s) {
      return String(s ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function computeHeat(heat) {
      const sigs = (heat && Array.isArray(heat.signals)) ? heat.signals : [];
      if (!sigs.length) return { score: null, coverage: 0 };
      let cit = null, votes = null, comments = null, stars = null;
      for (const s of sigs) {
        if (typeof s.count !== "number") continue;
        if (s.kind === "citations") cit = cit === null ? s.count : Math.max(cit, s.count);
        if (s.kind === "votes") votes = votes === null ? s.count : Math.max(votes, s.count);
        if (s.kind === "comments") comments = comments === null ? s.count : Math.max(comments, s.count);
        if (s.kind === "stars") stars = stars === null ? s.count : Math.max(stars, s.count);
      }
      let total = 0, cov = 0;
      if (cit !== null) { total += cit * 3; cov++; }
      if (votes !== null || comments !== null) { total += Math.max(votes || 0, (comments || 0) * 2); cov++; }
      if (stars !== null) { total += stars * 0.1; cov++; }
      return cov ? { score: Math.round(total), coverage: cov } : { score: null, coverage: 0 };
    }

    function matchesFilter(paper, sec) {
      const tier = paper.reading_tier || "deep";
      const tags = paper.tags || [];
      if (activeFilter === "deep" && tier !== "deep") return false;
      if (activeFilter === "scan" && tier !== "scan") return false;
      if (activeFilter === "tier1" && sec.priority !== "tier1") return false;
      if (activeFilter === "open" && !paper.repo_url && !tags.includes("open-code") && !tags.includes("open-env")) return false;
      if (activeFilter === "online-rl" && !tags.includes("online-rl")) return false;
      if (activeFilter === "backlist" && paper.lane !== "popular_backlist" && paper.lane !== "award") return false;
      if (searchQuery) {
        const hay = [
          paper.title, paper.intro, paper.abstract_zh, paper.method, paper.results,
          paper.authors_or_org, ...(tags), ...(paper.directions || []), ...(paper.secondary_topics || [])
        ].join(" ").toLowerCase();
        if (!hay.includes(searchQuery)) return false;
      }
      return true;
    }

    function renderHeatSignals(paper) {
      const heat = paper.heat || {};
      const sigs = heat.signals || [];
      if (!sigs.length) {
        return `<p>${esc(heat.unavailable || "暂无可核验外部热度数据")}</p>`;
      }
      const kindMap = { citations: "学术引用", votes: "社区投票", comments: "社区评论", stars: "GitHub 星标" };
      const items = sigs.map(s =>
        `<li><strong>${kindMap[s.kind] || s.kind}</strong>：${esc(s.source)} ${s.approximate ? "约 " : ""}${s.count}（${esc(s.observed_on)}） · <a href="${esc(s.url)}" target="_blank" rel="noopener">来源</a>${s.note ? " — " + esc(s.note) : ""}</li>`
      ).join("");
      return `<ul style="margin:4px 0 0 18px;padding:0;">${items}</ul>`;
    }

    function render() {
      const issue = ISSUES[currentIdx];
      if (!issue) return;

      const allPapers = [];
      for (const sec of issue.sections) {
        for (const p of sec.papers) allPapers.push({ paper: p, sec });
      }
      const leadObj = allPapers.find(x => x.paper.id === issue.lead.paper_id);

      document.getElementById("subtitle").textContent =
        `期号 ${issue.date}（${issue.timezone}） · 共收录 ${allPapers.length} 篇（深读 ${allPapers.filter(x => (x.paper.reading_tier || "deep") === "deep").length} / 速览 ${allPapers.filter(x => x.paper.reading_tier === "scan").length}）`;

      const leadHtml = `
        <div class="lead-card">
          <div class="lead-label">今日首推 · Lead Pick</div>
          <div class="lead-title">
            ${leadObj ? `<a href="${esc(leadObj.paper.url)}" target="_blank" rel="noopener">${esc(leadObj.paper.title)}</a>` : esc(issue.lead.paper_id)}
          </div>
          <p class="lead-reason">${esc(issue.lead.reason)}${issue.lead.section_ref ? ` · 重点章节：<strong>${esc(issue.lead.section_ref)}</strong>` : ""}</p>
        </div>`;
      document.getElementById("leadContainer").innerHTML = leadHtml;

      const navParts = [];
      const secParts = [];
      let visibleCount = 0;

      issue.sections.forEach((sec, idx) => {
        const filtered = sec.papers.filter(p => matchesFilter(p, sec));
        visibleCount += filtered.length;
        navParts.push(`<a href="#topic-${idx}">${esc(sec.topic)}<span class="cnt">${filtered.length}</span></a>`);

        const prioBadge = sec.priority === "tier1"
          ? `<span class="badge tier1">Tier 1 核心主线</span>`
          : sec.priority === "tier2"
            ? `<span class="badge tier2">Tier 2 雷达追踪</span>`
            : "";

        const noteHtml = sec.note ? `<div class="topic-note">${esc(sec.note)}</div>` : "";
        const cardsHtml = filtered.length ? filtered.map(p => {
          const tier = p.reading_tier || "deep";
          const h = computeHeat(p.heat);
          const heatText = h.score === null ? "热度 — (0/3)" : `热度 ${h.score} (${h.coverage}/3)`;
          const dirBadges = (p.directions || []).map(d => `<span class="badge lane">${esc(d)}</span>`).join("");
          const tagBadges = (p.tags || []).map(t => {
            const cls = (t === "offline-only" || t === "no-code-yet") ? "badge warn" : "badge tag";
            return `<span class="${cls}">${esc(t)}</span>`;
          }).join("");
          const secTags = (p.secondary_topics || []).map(t => `<span class="badge tag">关联:${esc(t)}</span>`).join("");
          const laneBadge = p.lane !== "fresh" ? `<span class="badge lane">${esc(LANE_LABELS[p.lane] || p.lane)}</span>` : "";
          const awardHtml = p.award
            ? `<div class="detail-block"><h4>官方奖项（不计入热度）</h4><p>${esc(p.award.venue)} ${p.award.year} · ${esc(p.award.name)}（${esc(p.award.scope)}） · <a href="${esc(p.award.url)}" target="_blank" rel="noopener">官方记录</a></p></div>`
            : "";
          const backlistHtml = (p.backlist_evidence && p.backlist_evidence.length)
            ? `<div class="detail-block"><h4>高热老作入选依据</h4><ul style="margin:4px 0 0 18px;padding:0;">${p.backlist_evidence.map(e => `<li>${esc(e.summary)} · <a href="${esc(e.url)}" target="_blank" rel="noopener">证据</a></li>`).join("")}</ul></div>`
            : "";

          return `
            <article class="paper-card is-${tier}" id="paper-${esc(p.id)}">
              <div class="paper-top">
                <h3 class="paper-title"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a></h3>
                <span class="heat-pill" title="Heat v1 = 引用×3 + max(投票×1, 评论×2) + Star×0.1">${heatText}</span>
              </div>
              <div class="paper-meta">
                <span class="badge ${tier}">${tier === "deep" ? "深度精读" : "新作速览"}</span>
                ${laneBadge}
                ${dirBadges}
                <span>${esc(p.published_on)}</span>
                ${p.authors_or_org ? `<span>· ${esc(p.authors_or_org)}</span>` : ""}
                <a href="${esc(p.url)}" target="_blank" rel="noopener">原文直链 ↗</a>
                ${p.repo_url ? `<a href="${esc(p.repo_url)}" target="_blank" rel="noopener">官方代码 ↗</a>` : ""}
              </div>
              <p class="paper-intro">${esc(p.intro)}</p>
              <div class="paper-meta">${tagBadges}${secTags}</div>
              ${p.revision_note ? `<div class="topic-note" style="margin-top:8px;">版本修订：${esc(p.revision_note)}</div>` : ""}
              <details class="paper-details" ${allExpanded ? "open" : ""}>
                <summary>展开详情（摘要译述 · 方法论 · 实验结果 · 局限 · 热度明细）</summary>
                <div class="detail-grid">
                  <div class="detail-block"><h4>摘要译述</h4><p>${esc(p.abstract_zh)}</p></div>
                  <div class="detail-block"><h4>方法论</h4><p>${esc(p.method)}</p></div>
                  <div class="detail-block"><h4>实验结果</h4><p>${esc(p.results)}</p></div>
                  <div class="detail-block"><h4>关键局限</h4><p>${esc(p.limitation)}</p></div>
                  <div class="detail-block"><h4>热度明细</h4>${renderHeatSignals(p)}</div>
                  ${awardHtml}
                  ${backlistHtml}
                </div>
              </details>
            </article>`;
        }).join("") : `<div class="empty-msg">当前筛选条件下本栏暂无条目。</div>`;

        secParts.push(`
          <section class="topic-block" id="topic-${idx}">
            <div class="topic-header">
              <h2>${esc(sec.topic)}</h2>
              ${prioBadge}
              <span style="color:var(--muted);font-size:0.86rem;">${filtered.length} 篇</span>
            </div>
            ${noteHtml}
            ${cardsHtml}
          </section>`);
      });

      document.getElementById("topicNav").innerHTML = navParts.join("");
      document.getElementById("content").innerHTML = secParts.join("");
      document.getElementById("statsFooter").textContent =
        `当前显示 ${visibleCount} / ${allPapers.length} 篇 · 书架已归档 ${ISSUES.length} 期`;
    }

    ISSUES.forEach((iss, i) => {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = `${iss.date}（${iss.sections.reduce((a, s) => a + s.papers.length, 0)} 篇）`;
      dateSelect.appendChild(opt);
    });

    dateSelect.addEventListener("change", () => {
      currentIdx = Number(dateSelect.value);
      render();
    });

    document.getElementById("filterPills").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-filter]");
      if (!btn) return;
      activeFilter = btn.dataset.filter;
      document.querySelectorAll("#filterPills .pill").forEach(b => b.classList.toggle("active", b === btn));
      render();
    });

    searchInput.addEventListener("input", () => {
      searchQuery = searchInput.value.trim().toLowerCase();
      render();
    });

    toggleExpandBtn.addEventListener("click", () => {
      allExpanded = !allExpanded;
      toggleExpandBtn.textContent = allExpanded ? "折叠为导读速扫" : "展开全部详情";
      document.querySelectorAll("details.paper-details").forEach(d => { d.open = allExpanded; });
    });

    themeBtn.addEventListener("click", () => {
      const isDark = document.documentElement.getAttribute("data-theme") === "dark";
      document.documentElement.setAttribute("data-theme", isDark ? "light" : "dark");
      themeBtn.textContent = isDark ? "切换深色" : "切换浅色";
    });

    render();
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Daily Paper issues to HTML or legacy JSON.")
    parser.add_argument("--issues-dir", type=Path, help="Directory of archived issues/*.json")
    parser.add_argument("--issue", type=Path, help="Single issue JSON file to render")
    parser.add_argument("--export-legacy", type=Path, help="Export a single issue JSON into legacy bookshelf format")
    parser.add_argument("--output", type=Path, help="Output file path (HTML or legacy JSON)")
    args = parser.parse_args()

    if args.export_legacy:
        issue = json.loads(args.export_legacy.read_text(encoding="utf-8"))
        legacy = to_legacy_issue(issue)
        rendered = json.dumps(legacy, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print(f"Exported legacy JSON to {args.output}")
        else:
            print(rendered)
        return 0

    issues: list[dict[str, Any]] = []
    if args.issue:
        issues.append(json.loads(args.issue.read_text(encoding="utf-8")))
    else:
        idir = args.issues_dir or (REPO_ROOT / "issues")
        for p in sorted(idir.glob("*.json"), reverse=True):
            issues.append(json.loads(p.read_text(encoding="utf-8")))

    if not issues:
        print("Error: no issue JSON files found to render. Pass --issue or populate issues/.", file=sys.stderr)
        return 1

    issues.sort(key=lambda x: str(x.get("date", "")), reverse=True)
    # Escape closing script tags safely for inline JSON embedding
    embedded_json = json.dumps(issues, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__ISSUES_JSON__", embedded_json)

    out = args.output or (REPO_ROOT / "dist" / "index.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Rendered {len(issues)} issue(s) to {out} ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
