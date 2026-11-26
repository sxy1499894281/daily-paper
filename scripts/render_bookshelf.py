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
  <title>研究论文书架 · Daily Paper</title>
  <style>
    :root {
      --bg: #f7f5ee;
      --surface: #fcfbf7;
      --surface-warm: #f2eee4;
      --surface-sage: #eff3ec;
      --surface-terra: #f2e8de;
      --ink: #22211e;
      --ink-2: #55524b;
      --ink-muted: #868075;
      --rule: #e6e1d5;
      --rule-strong: #d3ccb9;
      --sage: #2e5944;
      --sage-soft: #e7efe6;
      --terra: #8f4730;
      --terra-soft: #f5ebe3;
      --seal: #993e2e;
      --shelf-top: #a4805c;
      --shelf-bot: #8a6744;
      --serif: "Songti SC", "STSong", "Noto Serif SC", "Source Serif 4", "Iowan Old Style", Georgia, serif;
      --sans: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Inter", sans-serif;
      --mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;

      /* 8 pastel Morandi book cover hues */
      --book-0: #dce5d7;
      --book-1: #ede3ce;
      --book-2: #dce3e8;
      --book-3: #eadad4;
      --book-4: #e4e0ef;
      --book-5: #ece5ce;
      --book-6: #d9e5dc;
      --book-7: #e8e0d7;
    }
    [data-theme="dark"] {
      --bg: #151513;
      --surface: #1c1b18;
      --surface-warm: #23211d;
      --surface-sage: #1c241e;
      --surface-terra: #28201b;
      --ink: #eae6dd;
      --ink-2: #bab4a7;
      --ink-muted: #847e73;
      --rule: #2b2924;
      --rule-strong: #3d3932;
      --sage: #8ab89f;
      --sage-soft: #1f2e25;
      --terra: #d98c72;
      --terra-soft: #2e221d;
      --seal: #cf7666;
      --shelf-top: #6e553c;
      --shelf-bot: #543f2a;

      --book-0: #283329;
      --book-1: #363024;
      --book-2: #262f36;
      --book-3: #362926;
      --book-4: #2d2a38;
      --book-5: #343023;
      --book-6: #243129;
      --book-7: #312c27;
    }

    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: var(--sans);
      font-size: 14.5px;
      line-height: 1.72;
      -webkit-font-smoothing: antialiased;
    }

    a {
      color: var(--sage);
      text-decoration: none;
      transition: color 0.15s ease, opacity 0.15s ease;
    }
    a:hover { opacity: 0.8; }

    /* Top quiet bar */
    .topbar {
      border-bottom: 1px solid var(--rule);
      background: var(--bg);
    }
    .topbar-inner {
      max-width: 1000px;
      margin: 0 auto;
      padding: 11px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 0.84rem;
    }
    .topbar-brand {
      color: var(--sage);
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    .topbar-right {
      display: flex;
      align-items: center;
      gap: 14px;
      color: var(--ink-muted);
      font-size: 0.8rem;
    }
    .ghost-btn {
      background: none;
      border: none;
      padding: 2px 4px;
      font: inherit;
      color: var(--ink-muted);
      cursor: pointer;
    }
    .ghost-btn:hover { color: var(--ink); }

    .container {
      max-width: 1000px;
      margin: 0 auto;
      padding: 36px 24px 80px;
    }

    /* Hero Masthead with tilted square seal */
    .hero {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 24px;
    }
    .hero-eyebrow {
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--terra);
      letter-spacing: 0.06em;
      margin-bottom: 6px;
    }
    .hero-title {
      margin: 0;
      font-family: var(--serif);
      font-size: 2.35rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      line-height: 1.18;
      color: var(--ink);
    }
    .hero-sub {
      margin: 10px 0 0;
      color: var(--ink-2);
      font-size: 0.9rem;
    }
    .seal-stamp {
      flex-shrink: 0;
      width: 48px;
      height: 48px;
      margin-top: 14px;
      border: 1.5px solid var(--seal);
      border-radius: 3px;
      padding: 2px;
      transform: rotate(-7deg);
      color: var(--seal);
      opacity: 0.86;
      user-select: none;
    }
    .seal-stamp-inner {
      width: 100%;
      height: 100%;
      border: 1px solid var(--seal);
      display: grid;
      grid-template-columns: 1fr 1fr;
      align-items: center;
      justify-items: center;
      font-family: var(--serif);
      font-size: 12px;
      font-weight: 700;
      line-height: 1.05;
      padding: 2px;
    }

    /* Archive Date Row */
    .archive-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 0;
      border-top: 1px solid var(--rule);
      border-bottom: 1px solid var(--rule);
      margin-bottom: 22px;
      font-size: 0.84rem;
      color: var(--ink-2);
    }
    .archive-left, .archive-right {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }
    .paper-select, .paper-btn {
      font-family: var(--sans);
      font-size: 0.82rem;
      color: var(--ink);
      background: var(--surface);
      border: 1px solid var(--rule-strong);
      border-radius: 4px;
      padding: 5px 10px;
      cursor: pointer;
      transition: border-color 0.15s ease, background 0.15s ease;
    }
    .paper-select { font-family: var(--mono); font-size: 0.8rem; }
    .paper-btn:hover, .paper-select:hover { border-color: var(--ink-2); }
    .paper-btn:disabled { opacity: 0.42; cursor: not-allowed; }
    .archive-count {
      font-family: var(--mono);
      font-size: 0.82rem;
      color: var(--ink-2);
      margin-right: 4px;
    }

    /* Illustrated Pastel Bookshelf */
    .shelf-section { margin-bottom: 26px; }
    .shelf-caption {
      font-size: 0.8rem;
      color: var(--ink-muted);
      margin-bottom: 10px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .bookshelf-wrap {
      overflow-x: auto;
      padding-top: 10px;
      padding-bottom: 4px;
    }
    .books-row {
      display: grid;
      grid-template-columns: repeat(8, minmax(100px, 1fr));
      gap: 10px;
      align-items: end;
      padding: 0 6px;
    }
    .book-cover {
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      height: 146px;
      padding: 11px 10px 10px 14px;
      border-radius: 3px 5px 2px 2px;
      border: 1px solid rgba(34, 33, 30, 0.1);
      color: var(--ink);
      position: relative;
      box-shadow:
        inset 6px 0 0 rgba(0, 0, 0, 0.045),
        inset 7px 0 0 rgba(255, 255, 255, 0.42),
        0 2px 5px rgba(38, 30, 20, 0.06);
      transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.22s ease;
      cursor: pointer;
    }
    .book-cover:hover {
      transform: translateY(-7px) rotate(-1deg);
      box-shadow:
        inset 6px 0 0 rgba(0, 0, 0, 0.05),
        inset 7px 0 0 rgba(255, 255, 255, 0.48),
        0 10px 18px rgba(45, 34, 22, 0.13);
      color: var(--ink);
      opacity: 1;
    }
    .book-cover.is-active {
      transform: translateY(-6px) rotate(-1.4deg);
      box-shadow:
        inset 6px 0 0 rgba(0, 0, 0, 0.06),
        inset 7px 0 0 rgba(255, 255, 255, 0.5),
        0 9px 16px rgba(45, 34, 22, 0.14);
    }
    .book-cover.c-0 { background: var(--book-0); }
    .book-cover.c-1 { background: var(--book-1); }
    .book-cover.c-2 { background: var(--book-2); }
    .book-cover.c-3 { background: var(--book-3); }
    .book-cover.c-4 { background: var(--book-4); }
    .book-cover.c-5 { background: var(--book-5); }
    .book-cover.c-6 { background: var(--book-6); }
    .book-cover.c-7 { background: var(--book-7); }

    .book-en {
      font-size: 0.69rem;
      line-height: 1.25;
      color: var(--ink-2);
      opacity: 0.82;
    }
    .book-zh {
      font-family: var(--serif);
      font-size: 1.04rem;
      font-weight: 700;
      line-height: 1.3;
      color: var(--ink);
      margin: 4px 0;
    }
    .book-foot {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 0.72rem;
      color: var(--ink-2);
      opacity: 0.85;
    }
    .book-tier-dot {
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: var(--sage);
      opacity: 0.75;
    }
    .shelf-plank {
      height: 6px;
      background: linear-gradient(180deg, var(--shelf-top) 0%, var(--shelf-bot) 100%);
      border-radius: 2px;
      box-shadow: 0 3px 8px rgba(74, 52, 30, 0.18);
      margin-top: 2px;
    }

    /* Lead Pick Card */
    .lead-box {
      background: var(--surface);
      border: 1px solid var(--rule);
      border-left: 3px solid var(--sage);
      border-radius: 3px;
      padding: 18px 22px;
      margin-bottom: 18px;
    }
    .lead-label {
      font-size: 0.78rem;
      font-weight: 600;
      color: var(--terra);
      margin-bottom: 6px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .lead-label .ref {
      font-weight: 400;
      color: var(--ink-muted);
      font-family: var(--mono);
      font-size: 0.74rem;
    }
    .lead-title {
      margin: 0 0 6px;
      font-family: var(--serif);
      font-size: 1.15rem;
      font-weight: 700;
      color: var(--ink);
      line-height: 1.38;
    }
    .lead-reason {
      margin: 0 0 12px;
      font-size: 0.89rem;
      color: var(--ink-2);
    }
    .lead-links {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      font-size: 0.83rem;
    }
    .lead-links a {
      color: var(--sage);
      border-bottom: 1px solid var(--sage);
      padding-bottom: 1px;
    }

    /* Heat Formula Collapsible */
    details.heat-guide {
      margin-bottom: 16px;
      font-size: 0.83rem;
      color: var(--ink-2);
    }
    details.heat-guide summary {
      cursor: pointer;
      color: var(--sage);
      font-weight: 500;
      user-select: none;
      display: inline-block;
    }
    .heat-guide-body {
      margin-top: 8px;
      padding: 12px 16px;
      background: var(--surface);
      border: 1px solid var(--rule);
      border-radius: 4px;
      font-size: 0.82rem;
      color: var(--ink-2);
      line-height: 1.7;
    }
    .heat-guide-body code {
      font-family: var(--mono);
      font-size: 0.78rem;
      background: var(--surface-warm);
      padding: 1px 5px;
      border-radius: 3px;
    }

    /* Filter & Utility Strip */
    .filter-strip {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 28px;
    }
    .filter-pills {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      align-items: center;
    }
    .f-pill {
      font-family: var(--sans);
      font-size: 0.81rem;
      color: var(--ink-2);
      background: var(--surface);
      border: 1px solid var(--rule-strong);
      border-radius: 4px;
      padding: 4px 10px;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .f-pill:hover { border-color: var(--sage); color: var(--ink); }
    .f-pill.active {
      background: var(--sage-soft);
      border-color: var(--sage);
      color: var(--sage);
      font-weight: 600;
    }
    .f-pill .cnt {
      font-family: var(--mono);
      font-size: 0.74rem;
      opacity: 0.75;
      margin-left: 4px;
    }
    .filter-tools {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }
    .tool-toggle {
      font-family: var(--sans);
      font-size: 0.79rem;
      color: var(--ink-2);
      background: transparent;
      border: 1px solid var(--rule-strong);
      border-radius: 4px;
      padding: 4px 9px;
      cursor: pointer;
    }
    .tool-toggle.active {
      background: var(--surface-warm);
      border-color: var(--ink-2);
      color: var(--ink);
    }
    .search-input {
      font-family: var(--sans);
      font-size: 0.82rem;
      color: var(--ink);
      background: var(--surface);
      border: 1px solid var(--rule-strong);
      border-radius: 4px;
      padding: 4px 10px;
      width: 175px;
      outline: none;
    }
    .search-input:focus { border-color: var(--sage); }

    /* 2-Column Editorial Grid */
    .topics-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 44px 48px;
      align-items: start;
    }

    section.topic-col {
      scroll-margin-top: 24px;
      min-width: 0;
    }
    .topic-eyebrow {
      font-size: 0.75rem;
      color: var(--ink-muted);
      letter-spacing: 0.02em;
    }
    .topic-title-row {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 10px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--rule-strong);
      margin-bottom: 12px;
    }
    .topic-h2 {
      margin: 2px 0 0;
      font-family: var(--serif);
      font-size: 1.38rem;
      font-weight: 700;
      color: var(--ink);
    }
    .topic-cnt {
      font-size: 0.82rem;
      color: var(--ink-muted);
      white-space: nowrap;
    }
    .topic-note {
      margin: 0 0 14px;
      font-size: 0.84rem;
      color: var(--ink-2);
      line-height: 1.65;
    }

    /* Lane Sub-group Ribbon */
    .lane-group { margin-bottom: 18px; }
    .lane-ribbon {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 5px 10px;
      margin-bottom: 6px;
      border-radius: 2px;
      font-size: 0.8rem;
      font-weight: 600;
      background: var(--surface-warm);
      border-left: 2.5px solid var(--sage);
      color: var(--ink);
    }
    .lane-ribbon.lane-backlist {
      background: var(--surface-terra);
      border-left-color: var(--terra);
      color: var(--terra);
    }
    .lane-ribbon.lane-award, .lane-ribbon.lane-supplement {
      background: var(--surface-warm);
      border-left-color: var(--ink-muted);
      color: var(--ink-2);
    }
    .lane-ribbon .l-cnt {
      font-weight: 400;
      color: var(--ink-muted);
      font-size: 0.76rem;
    }

    /* Paper Entry Row */
    article.paper-row {
      padding: 12px 0;
      border-bottom: 1px solid var(--rule);
      scroll-margin-top: 28px;
    }
    article.paper-row:last-child { border-bottom-color: var(--rule); }

    .row-meta-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-family: var(--mono);
      font-size: 0.75rem;
      color: var(--ink-muted);
      margin-bottom: 4px;
    }
    .meta-left {
      display: flex;
      align-items: center;
      gap: 7px;
      flex-wrap: wrap;
    }
    .tier-dot-txt {
      font-family: var(--sans);
      font-size: 0.72rem;
      color: var(--ink-muted);
    }
    .tier-dot-txt.deep { color: var(--sage); }

    .row-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }
    .paper-title-btn {
      flex: 1;
      text-align: left;
      background: none;
      border: none;
      padding: 0;
      margin: 0;
      font-family: var(--sans);
      font-size: 0.96rem;
      font-weight: 650;
      line-height: 1.46;
      color: var(--ink);
      cursor: pointer;
    }
    .paper-title-btn:hover { color: var(--sage); }

    /* Flame Heat Button (matches reference screenshots!) */
    .heat-flame-btn {
      flex-shrink: 0;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 3px 8px;
      border-radius: 4px;
      border: 1px solid transparent;
      background: transparent;
      font-family: var(--mono);
      font-size: 0.78rem;
      color: var(--ink-muted);
      cursor: pointer;
      transition: all 0.15s ease;
      line-height: 1.2;
    }
    .heat-flame-btn:hover {
      background: var(--surface-warm);
      border-color: var(--rule-strong);
    }
    .heat-flame-btn.has-heat {
      color: var(--terra);
    }
    .heat-flame-btn.is-hot, .heat-flame-btn.open {
      background: var(--terra-soft);
      border-color: rgba(143, 71, 48, 0.22);
      color: var(--terra);
      font-weight: 600;
    }
    .heat-flame-btn.no-heat.open {
      background: var(--surface-warm);
      border-color: var(--rule-strong);
      color: var(--ink-2);
    }
    .flame-svg {
      width: 13px;
      height: 13px;
      fill: none;
      stroke: currentColor;
      stroke-width: 1.7;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    /* Optional 1-2 line quiet intro preview under title */
    .row-intro-preview {
      margin: 6px 0 0;
      font-size: 0.84rem;
      color: var(--ink-2);
      line-height: 1.6;
    }
    body.compact-mode .row-intro-preview { display: none; }

    /* Inline Heat Breakdown Panel ("细分热度") */
    .heat-panel {
      display: none;
      margin-top: 10px;
      padding: 10px 12px;
      background: var(--surface-warm);
      border-radius: 3px;
      font-size: 0.8rem;
      color: var(--ink-2);
    }
    .heat-panel.open { display: block; }
    .heat-panel-head {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 7px;
      font-size: 0.78rem;
    }
    .heat-panel-head strong { color: var(--ink); font-weight: 600; }
    .heat-panel-head span { color: var(--ink-muted); }
    .heat-table {
      display: grid;
      grid-template-columns: 62px minmax(0, 1fr);
      gap: 5px 10px;
      align-items: baseline;
    }
    .ht-label { color: var(--ink-muted); font-size: 0.78rem; }
    .ht-val { color: var(--ink-2); font-size: 0.79rem; line-height: 1.5; }
    .ht-val a {
      color: var(--sage);
      text-decoration: underline;
      text-underline-offset: 2px;
    }
    .ht-miss { color: var(--ink-muted); }

    /* Full Reading Panel (opened on title click) */
    .reading-panel {
      display: none;
      margin-top: 12px;
    }
    .reading-panel.open { display: block; }

    .dir-line {
      font-size: 0.79rem;
      color: var(--ink-muted);
      margin-bottom: 8px;
    }
    .intro-callout {
      padding: 11px 14px;
      background: var(--surface-sage);
      border-left: 2.5px solid var(--sage);
      border-radius: 2px;
      margin-bottom: 14px;
    }
    .intro-callout-label {
      font-size: 0.78rem;
      font-weight: 700;
      color: var(--sage);
      margin-bottom: 4px;
    }
    .intro-callout p {
      margin: 0;
      font-size: 0.87rem;
      color: var(--ink);
      line-height: 1.68;
    }

    .read-block { margin-bottom: 13px; }
    .read-block-title {
      font-size: 0.79rem;
      font-weight: 700;
      color: var(--ink-2);
      margin-bottom: 3px;
    }
    .read-block p {
      margin: 0;
      font-size: 0.85rem;
      color: var(--ink-2);
      line-height: 1.72;
    }

    .read-footer {
      margin-top: 12px;
      padding-top: 10px;
      border-top: 1px dashed var(--rule-strong);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 0.79rem;
    }
    .read-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
    }
    .r-tag {
      font-family: var(--mono);
      font-size: 0.71rem;
      color: var(--ink-muted);
      background: var(--surface-warm);
      padding: 1px 6px;
      border-radius: 3px;
    }
    .r-tag.warn { color: var(--terra); background: var(--terra-soft); }
    .read-links {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .read-links a {
      color: var(--sage);
      border-bottom: 1px solid var(--sage);
      padding-bottom: 1px;
    }
    .star-inline {
      background: none;
      border: 1px solid var(--rule-strong);
      border-radius: 4px;
      padding: 2px 8px;
      font-size: 0.77rem;
      color: var(--ink-2);
      cursor: pointer;
    }
    .star-inline.starred {
      border-color: var(--terra);
      color: var(--terra);
      background: var(--terra-soft);
    }

    .empty-msg {
      padding: 12px 0;
      font-size: 0.84rem;
      color: var(--ink-muted);
    }

    /* Footer */
    footer.colophon {
      margin-top: 56px;
      padding-top: 16px;
      border-top: 1px solid var(--rule);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      font-size: 0.79rem;
      color: var(--ink-muted);
    }
    .toast {
      position: fixed;
      bottom: 22px;
      right: 22px;
      background: var(--ink);
      color: var(--bg);
      padding: 8px 14px;
      border-radius: 5px;
      font-size: 0.82rem;
      opacity: 0;
      transform: translateY(8px);
      pointer-events: none;
      transition: all 0.2s ease;
      z-index: 200;
    }
    .toast.show { opacity: 1; transform: translateY(0); }

    @media (max-width: 820px) {
      .topics-grid { grid-template-columns: 1fr; gap: 34px; }
      .hero-title { font-size: 1.85rem; }
      .container { padding: 24px 16px 64px; }
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="topbar-inner">
      <a class="topbar-brand" href="#">论文书架</a>
      <div class="topbar-right">
        <span>每日研究简报</span>
        <button class="ghost-btn" id="themeBtn" type="button">深色</button>
      </div>
    </div>
  </div>

  <div class="container">
    <header class="hero">
      <div>
        <div class="hero-eyebrow" id="heroEyebrow">八个研究方向</div>
        <h1 class="hero-title">研究论文书架</h1>
        <p class="hero-sub">先从书架选方向，再看近期新作、高热老作或获奖与专题补读。</p>
      </div>
      <div class="seal-stamp" aria-hidden="true">
        <div class="seal-stamp-inner">
          <span>論</span><span>文</span>
          <span>書</span><span>架</span>
        </div>
      </div>
    </header>

    <div class="archive-row">
      <div class="archive-left">
        <span>归档日期</span>
        <select class="paper-select" id="dateSelect" aria-label="选择归档日期"></select>
        <button class="paper-btn" id="jumpDateBtn" type="button">查看</button>
      </div>
      <div class="archive-right">
        <span class="archive-count" id="issueCount">本期 0 篇</span>
        <button class="paper-btn" id="prevIssueBtn" type="button">较早一期</button>
        <button class="paper-btn" id="nextIssueBtn" type="button">较新一期</button>
      </div>
    </div>

    <section class="shelf-section">
      <div class="shelf-caption">
        <span>主题书架</span>
        <span id="shelfHint" style="font-size:0.75rem;">点击书脊直达栏目</span>
      </div>
      <div class="bookshelf-wrap">
        <div class="books-row" id="booksRow"></div>
        <div class="shelf-plank"></div>
      </div>
    </section>

    <div id="leadContainer"></div>

    <details class="heat-guide">
      <summary>热度怎么算？</summary>
      <div class="heat-guide-body">
        热度采用 <strong>Heat v1</strong>（仅计入已核验的一手数据，无封顶）：
        <code>总分 = 四舍五入( 学术引用 × 3 + max(社区投票 × 1, 社区评论 × 2) + 官方仓库星标 × 0.1 )</code>。
        缺项不按 0 计入，仅标覆盖度（0/3–3/3）；真实的 0 正常显示；近期新作常处于冷启动期显示「—」，请结合导读与标签判断，不要把热度误读为研究质量排名。点击每篇标题右侧的火焰数值即可就地查看三维「细分热度」及可点击核验来源。
      </div>
    </details>

    <div class="filter-strip">
      <div class="filter-pills" id="filterPills"></div>
      <div class="filter-tools">
        <button class="tool-toggle active" id="introToggleBtn" type="button" title="切换是否直接显示导读预览">显示导读</button>
        <button class="tool-toggle" id="sortHeatBtn" type="button" title="按热度从高到低排序">热度 ↓</button>
        <input class="search-input" id="searchInput" type="search" placeholder="搜索标题、导读、标签..." />
      </div>
    </div>

    <main class="topics-grid" id="topicsGrid"></main>

    <footer class="colophon">
      <span id="footerStats"></span>
      <div style="display:flex;align-items:center;gap:10px;">
        <button class="paper-btn" id="exportStarBtn" type="button">复制收藏反馈 JSONL</button>
        <span>Daily Paper Skill · Schema v1.1</span>
      </div>
    </footer>
  </div>

  <div class="toast" id="toast"></div>

  <script id="issues-data" type="application/json">__ISSUES_JSON__</script>
  <script>
    const ISSUES = JSON.parse(document.getElementById("issues-data").textContent);

    const TOPIC_META = {
      "Computer Use": { en: "Computer Use", zh: "电脑操作" },
      "多模态编程": { en: "Multimodal Coding", zh: "多模态编程" },
      "GUI Agent": { en: "GUI Agents", zh: "GUI 智能体" },
      "环境规模化": { en: "Environment Scaling", zh: "环境规模化" },
      "递归自我改进": { en: "Self-Improvement", zh: "递归自我改进" },
      "游戏智能体": { en: "Game Agents", zh: "游戏智能体" },
      "World Model": { en: "World Model", zh: "世界模型" },
      "Personal Agent": { en: "Personal Agents", zh: "个人智能体" },
    };

    const STORAGE_KEY_STARS = "daily_paper_starred_v1";
    const STORAGE_KEY_THEME = "daily_paper_theme_v1";

    let currentIdx = 0;
    let activeFilter = "all";
    let activeBookIdx = 0;
    let sortByHeat = false;
    let showIntroPreview = true;
    let searchQuery = "";
    let starredMap = {};
    try { starredMap = JSON.parse(localStorage.getItem(STORAGE_KEY_STARS) || "{}"); } catch {}

    const dateSelect = document.getElementById("dateSelect");
    const prevIssueBtn = document.getElementById("prevIssueBtn");
    const nextIssueBtn = document.getElementById("nextIssueBtn");
    const introToggleBtn = document.getElementById("introToggleBtn");
    const sortHeatBtn = document.getElementById("sortHeatBtn");
    const searchInput = document.getElementById("searchInput");
    const themeBtn = document.getElementById("themeBtn");
    const toastEl = document.getElementById("toast");

    const FLAME_ICON = `<svg class="flame-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3c.5 3.5-2.5 5.3-2.5 8.2a2.5 2.5 0 0 0 5 0c0-1.2-.5-2.2-1.2-3 2.7 1.3 4.7 4 4.7 7.1A6 6 0 0 1 6 15.3c0-3.5 2.4-6.3 6-12.3Z"/></svg>`;

    function showToast(msg) {
      toastEl.textContent = msg;
      toastEl.classList.add("show");
      clearTimeout(showToast._t);
      showToast._t = setTimeout(() => toastEl.classList.remove("show"), 2200);
    }

    function esc(s) {
      return String(s ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function analyzeHeat(heat) {
      const sigs = (heat && Array.isArray(heat.signals)) ? heat.signals : [];
      let citSig = null, voteSig = null, commSig = null, starSig = null;
      for (const s of sigs) {
        if (typeof s.count !== "number") continue;
        if (s.kind === "citations" && (!citSig || s.count > citSig.count)) citSig = s;
        if (s.kind === "votes" && (!voteSig || s.count > voteSig.count)) voteSig = s;
        if (s.kind === "comments" && (!commSig || s.count > commSig.count)) commSig = s;
        if (s.kind === "stars" && (!starSig || s.count > starSig.count)) starSig = s;
      }
      const citContrib = citSig ? citSig.count * 3 : null;
      let commContrib = null, primaryCommSig = null;
      if (voteSig || commSig) {
        const vScore = voteSig ? voteSig.count : 0;
        const cScore = commSig ? commSig.count * 2 : 0;
        if (cScore > vScore && commSig) { commContrib = cScore; primaryCommSig = commSig; }
        else { commContrib = vScore; primaryCommSig = voteSig || commSig; }
      }
      const starContrib = starSig ? starSig.count * 0.1 : null;
      let cov = 0, raw = 0;
      if (citContrib !== null) { raw += citContrib; cov++; }
      if (commContrib !== null) { raw += commContrib; cov++; }
      if (starContrib !== null) { raw += starContrib; cov++; }
      return {
        score: cov > 0 ? Math.round(raw) : null,
        coverage: cov,
        citSig, voteSig, commSig, primaryCommSig, starSig,
      };
    }

    function renderHeatTableHtml(paper) {
      const h = analyzeHeat(paper.heat);
      const citHtml = h.citSig
        ? `<a href="${esc(h.citSig.url)}" target="_blank" rel="noopener">学术引用 · ${esc(h.citSig.source)} ${h.citSig.approximate ? "约 " : ""}${h.citSig.count.toLocaleString()} 次（${esc(h.citSig.observed_on)}）</a>`
        : `<span class="ht-miss">暂无可核验数据</span>`;

      let commHtml = `<span class="ht-miss">暂无可核验数据</span>`;
      if (h.primaryCommSig) {
        const parts = [];
        if (h.voteSig) parts.push(`${h.voteSig.count} 票`);
        if (h.commSig) parts.push(`${h.commSig.count} 评`);
        commHtml = `<a href="${esc(h.primaryCommSig.url)}" target="_blank" rel="noopener">社区讨论 · ${esc(h.primaryCommSig.source)} ${parts.join(" / ")}（${esc(h.primaryCommSig.observed_on)}）</a>`;
      }

      const starHtml = h.starSig
        ? `<a href="${esc(h.starSig.url)}" target="_blank" rel="noopener">仓库关注 · ${esc(h.starSig.source)} ${h.starSig.approximate ? "约 " : ""}${h.starSig.count.toLocaleString()} 星（${esc(h.starSig.observed_on)}）</a>`
        : `<span class="ht-miss">暂无可核验数据</span>`;

      const awardLine = paper.award
        ? `<div class="ht-label">官方奖项</div><div class="ht-val"><a href="${esc(paper.award.url)}" target="_blank" rel="noopener">${esc(paper.award.venue)} ${paper.award.year} · ${esc(paper.award.name)}（不计入热度）</a></div>`
        : "";

      return `
        <div class="heat-panel-head">
          <strong>细分热度</strong>
          <span>已核实 ${h.coverage}/3 项</span>
        </div>
        <div class="heat-table">
          <div class="ht-label">学术引用</div><div class="ht-val">${citHtml}</div>
          <div class="ht-label">社区讨论</div><div class="ht-val">${commHtml}</div>
          <div class="ht-label">仓库关注</div><div class="ht-val">${starHtml}</div>
          ${awardLine}
        </div>`;
    }

    function matchesFilter(paper) {
      if (activeFilter === "fresh" && paper.lane !== "fresh") return false;
      if (activeFilter === "backlist" && paper.lane !== "popular_backlist") return false;
      if (activeFilter === "award_supp" && paper.lane !== "award" && paper.lane !== "supplement") return false;
      if (activeFilter === "deep" && (paper.reading_tier || "deep") !== "deep") return false;
      if (activeFilter === "starred" && !starredMap[paper.id]) return false;
      if (searchQuery) {
        const hay = [
          paper.title, paper.intro, paper.abstract_zh, paper.method, paper.results,
          paper.authors_or_org, ...(paper.tags || []), ...(paper.directions || [])
        ].join(" ").toLowerCase();
        if (!hay.includes(searchQuery)) return false;
      }
      return true;
    }

    function saveStars() {
      try { localStorage.setItem(STORAGE_KEY_STARS, JSON.stringify(starredMap)); } catch {}
    }

    function render() {
      const issue = ISSUES[currentIdx];
      if (!issue) return;

      document.body.classList.toggle("compact-mode", !showIntroPreview);

      const allPapers = [];
      for (const sec of issue.sections) {
        for (const p of sec.papers) allPapers.push({ paper: p, sec });
      }

      document.getElementById("heroEyebrow").textContent = `${issue.sections.length} 个研究方向`;
      document.getElementById("issueCount").textContent = `本期 ${allPapers.length} 篇`;
      prevIssueBtn.disabled = currentIdx >= ISSUES.length - 1;
      nextIssueBtn.disabled = currentIdx <= 0;

      // Render 8 pastel book covers on wooden shelf
      document.getElementById("booksRow").innerHTML = issue.sections.map((sec, idx) => {
        const meta = TOPIC_META[sec.topic] || { en: sec.topic, zh: sec.topic };
        const isT1 = sec.priority === "tier1";
        return `
          <a class="book-cover c-${idx % 8} ${idx === activeBookIdx ? "is-active" : ""}" href="#topic-${idx}" data-book-idx="${idx}">
            <div class="book-en">${esc(meta.en)}</div>
            <div class="book-zh">${esc(meta.zh)}</div>
            <div class="book-foot">
              <span>${sec.papers.length} 篇</span>
              ${isT1 ? `<span class="book-tier-dot" title="Tier 1 核心主线"></span>` : ""}
            </div>
          </a>`;
      }).join("");

      // Lead Pick card
      const leadObj = allPapers.find(x => x.paper.id === issue.lead.paper_id);
      document.getElementById("leadContainer").innerHTML = `
        <section class="lead-box">
          <div class="lead-label">
            <span>本期首推</span>
            ${issue.lead.section_ref ? `<span class="ref">· ${esc(issue.lead.section_ref)}</span>` : ""}
          </div>
          <h2 class="lead-title">${leadObj ? esc(leadObj.paper.title) : esc(issue.lead.paper_id)}</h2>
          <p class="lead-reason">${esc(issue.lead.reason)}</p>
          <div class="lead-links">
            ${leadObj ? `<a href="#paper-${esc(leadObj.paper.id)}" id="jumpLeadBtn" data-lead-id="${esc(leadObj.paper.id)}">看书架解读</a>` : ""}
            ${leadObj ? `<a href="${esc(leadObj.paper.url)}" target="_blank" rel="noopener">直接读原文</a>` : ""}
          </div>
        </section>`;

      // Filter pills with exact counts
      const freshCnt = allPapers.filter(x => x.paper.lane === "fresh").length;
      const backCnt = allPapers.filter(x => x.paper.lane === "popular_backlist").length;
      const awdCnt = allPapers.filter(x => x.paper.lane === "award" || x.paper.lane === "supplement").length;
      const deepCnt = allPapers.filter(x => (x.paper.reading_tier || "deep") === "deep").length;
      const starCnt = allPapers.filter(x => starredMap[x.paper.id]).length;

      const pillDefs = [
        { key: "all", label: "全部", cnt: allPapers.length },
        { key: "fresh", label: "近期新作", cnt: freshCnt },
        { key: "backlist", label: "高热老作", cnt: backCnt },
        ...(awdCnt > 0 ? [{ key: "award_supp", label: "获奖与专题补读", cnt: awdCnt }] : []),
        { key: "deep", label: "深度精读", cnt: deepCnt },
        { key: "starred", label: "★ 收藏", cnt: starCnt },
      ];
      document.getElementById("filterPills").innerHTML = pillDefs.map(p => `
        <button class="f-pill ${activeFilter === p.key ? "active" : ""}" data-filter="${p.key}" type="button">
          ${p.label}<span class="cnt">${p.cnt}</span>
        </button>`).join("");

      // Render 2-column magazine grid
      let visibleTotal = 0;
      const gridHtml = issue.sections.map((sec, idx) => {
        const meta = TOPIC_META[sec.topic] || { en: sec.topic, zh: sec.topic };
        let filtered = sec.papers.filter(matchesFilter);
        if (sortByHeat) {
          filtered = [...filtered].sort((a, b) => {
            const sa = analyzeHeat(a.heat).score ?? -1;
            const sb = analyzeHeat(b.heat).score ?? -1;
            return sb - sa;
          });
        }
        visibleTotal += filtered.length;

        const laneGroups = [
          { key: "fresh", label: "近期新作", cls: "lane-fresh", items: filtered.filter(p => p.lane === "fresh") },
          { key: "popular_backlist", label: "高热老作", cls: "lane-backlist", items: filtered.filter(p => p.lane === "popular_backlist") },
          { key: "award_supp", label: "获奖与专题补读", cls: "lane-award", items: filtered.filter(p => p.lane === "award" || p.lane === "supplement") },
        ].filter(g => g.items.length > 0);

        const groupsHtml = laneGroups.length ? laneGroups.map(g => `
          <div class="lane-group">
            <div class="lane-ribbon ${g.cls}">
              <span>${g.label}</span>
              <span class="l-cnt">${g.items.length} 篇</span>
            </div>
            ${g.items.map(p => {
              const h = analyzeHeat(p.heat);
              const scoreText = h.score === null ? "—" : h.score.toLocaleString();
              const flameCls = h.score === null ? "no-heat" : (h.score >= 50 ? "has-heat is-hot" : "has-heat");
              const tier = p.reading_tier || "deep";
              const isStarred = !!starredMap[p.id];
              const dirLine = (p.directions && p.directions.length)
                ? `<div class="dir-line">【方向：${esc(p.directions.join(" / "))}】</div>`
                : "";
              const tagsHtml = (p.tags || []).map(t => {
                const w = (t === "offline-only" || t === "no-code-yet") ? " warn" : "";
                return `<span class="r-tag${w}">${esc(t)}</span>`;
              }).join("");
              const backlistHtml = (p.backlist_evidence && p.backlist_evidence.length)
                ? `<div class="read-block"><div class="read-block-title">高热老作入选依据</div><p>${p.backlist_evidence.map(e => `${esc(e.summary)}（<a href="${esc(e.url)}" target="_blank" rel="noopener">核验 ↗</a>）`).join("；")}</p></div>`
                : "";

              return `
                <article class="paper-row" id="paper-${esc(p.id)}">
                  <div class="row-meta-top">
                    <div class="meta-left">
                      <span>${esc(p.published_on)}</span>
                      <span class="tier-dot-txt ${tier}">· ${tier === "deep" ? "精读" : "速览"}</span>
                    </div>
                  </div>
                  <div class="row-head">
                    <button class="paper-title-btn" type="button" data-toggle-read="${esc(p.id)}">${esc(p.title)}</button>
                    <button class="heat-flame-btn ${flameCls}" type="button" data-toggle-heat="${esc(p.id)}" title="点击查看三维细分热度">
                      ${FLAME_ICON}<span>${scoreText}</span>
                    </button>
                  </div>
                  <p class="row-intro-preview">${esc(p.intro)}</p>

                  <div class="heat-panel" id="heat-${esc(p.id)}">
                    ${renderHeatTableHtml(p)}
                  </div>

                  <div class="reading-panel" id="read-${esc(p.id)}">
                    ${dirLine}
                    <div class="intro-callout">
                      <div class="intro-callout-label">导读</div>
                      <p>${esc(p.intro)}</p>
                    </div>
                    <div class="read-block">
                      <div class="read-block-title">摘要译述</div>
                      <p>${esc(p.abstract_zh)}</p>
                    </div>
                    <div class="read-block">
                      <div class="read-block-title">方法论</div>
                      <p>${esc(p.method)}</p>
                    </div>
                    <div class="read-block">
                      <div class="read-block-title">实验结果</div>
                      <p>${esc(p.results)}</p>
                    </div>
                    <div class="read-block">
                      <div class="read-block-title">关键局限</div>
                      <p>${esc(p.limitation)}</p>
                    </div>
                    ${backlistHtml}
                    <div class="read-footer">
                      <div class="read-tags">${tagsHtml}</div>
                      <div class="read-links">
                        <button class="star-inline ${isStarred ? "starred" : ""}" type="button" data-star-id="${esc(p.id)}" data-star-title="${esc(p.title)}">${isStarred ? "★ 已收藏" : "☆ 收藏"}</button>
                        <a href="${esc(p.url)}" target="_blank" rel="noopener">直接读原文 ↗</a>
                        ${p.repo_url ? `<a href="${esc(p.repo_url)}" target="_blank" rel="noopener">代码仓库 ↗</a>` : ""}
                      </div>
                    </div>
                  </div>
                </article>`;
            }).join("")}
          </div>`).join("") : `<div class="empty-msg">当前筛选条件下本栏暂无条目。</div>`;

        return `
          <section class="topic-col" id="topic-${idx}">
            <div class="topic-eyebrow">${esc(meta.en)}</div>
            <div class="topic-title-row">
              <h2 class="topic-h2">${esc(meta.zh)}</h2>
              <span class="topic-cnt">${filtered.length} 篇</span>
            </div>
            ${sec.note ? `<p class="topic-note">${esc(sec.note)}</p>` : ""}
            ${groupsHtml}
          </section>`;
      }).join("");

      document.getElementById("topicsGrid").innerHTML = gridHtml;
      document.getElementById("footerStats").textContent =
        `当前显示 ${visibleTotal} / ${allPapers.length} 篇 · 书架共归档 ${ISSUES.length} 期`;
    }

    // Populate archive dropdown
    ISSUES.forEach((iss, i) => {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = i === 0 ? `${iss.date}（最新）` : iss.date;
      dateSelect.appendChild(opt);
    });

    document.getElementById("jumpDateBtn").addEventListener("click", () => {
      currentIdx = Number(dateSelect.value);
      render();
    });
    dateSelect.addEventListener("change", () => {
      currentIdx = Number(dateSelect.value);
      render();
    });
    prevIssueBtn.addEventListener("click", () => {
      if (currentIdx < ISSUES.length - 1) {
        currentIdx++;
        dateSelect.value = String(currentIdx);
        render();
      }
    });
    nextIssueBtn.addEventListener("click", () => {
      if (currentIdx > 0) {
        currentIdx--;
        dateSelect.value = String(currentIdx);
        render();
      }
    });

    // Book click active highlight
    document.getElementById("booksRow").addEventListener("click", (e) => {
      const a = e.target.closest("a[data-book-idx]");
      if (!a) return;
      activeBookIdx = Number(a.dataset.bookIdx);
      document.querySelectorAll(".book-cover").forEach((el, i) => el.classList.toggle("is-active", i === activeBookIdx));
    });

    // Lead jump & auto-expand
    document.getElementById("leadContainer").addEventListener("click", (e) => {
      const a = e.target.closest("#jumpLeadBtn");
      if (!a) return;
      const pid = a.dataset.leadId;
      const heatEl = document.getElementById("heat-" + pid);
      const readEl = document.getElementById("read-" + pid);
      if (heatEl) heatEl.classList.add("open");
      if (readEl) readEl.classList.add("open");
    });

    // Filter pills
    document.getElementById("filterPills").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-filter]");
      if (!btn) return;
      activeFilter = btn.dataset.filter;
      render();
    });

    introToggleBtn.addEventListener("click", () => {
      showIntroPreview = !showIntroPreview;
      introToggleBtn.classList.toggle("active", showIntroPreview);
      introToggleBtn.textContent = showIntroPreview ? "显示导读" : "极简目录";
      document.body.classList.toggle("compact-mode", !showIntroPreview);
    });

    sortHeatBtn.addEventListener("click", () => {
      sortByHeat = !sortByHeat;
      sortHeatBtn.classList.toggle("active", sortByHeat);
      render();
    });

    searchInput.addEventListener("input", () => {
      searchQuery = searchInput.value.trim().toLowerCase();
      render();
    });

    // Delegated clicks inside grid: flame heat toggle, paper title toggle, star toggle
    document.getElementById("topicsGrid").addEventListener("click", (e) => {
      const heatBtn = e.target.closest("button[data-toggle-heat]");
      if (heatBtn) {
        const pid = heatBtn.dataset.toggleHeat;
        const panel = document.getElementById("heat-" + pid);
        if (panel) {
          const isOpen = panel.classList.toggle("open");
          heatBtn.classList.toggle("open", isOpen);
        }
        return;
      }

      const readBtn = e.target.closest("button[data-toggle-read]");
      if (readBtn) {
        const pid = readBtn.dataset.toggleRead;
        const readPanel = document.getElementById("read-" + pid);
        const heatPanel = document.getElementById("heat-" + pid);
        if (readPanel) {
          const opening = readPanel.classList.toggle("open");
          if (opening && heatPanel) {
            heatPanel.classList.add("open");
            const hBtn = document.querySelector(`button[data-toggle-heat="${CSS.escape(pid)}"]`);
            if (hBtn) hBtn.classList.add("open");
          }
        }
        return;
      }

      const starBtn = e.target.closest("button[data-star-id]");
      if (starBtn) {
        const pid = starBtn.dataset.starId;
        const title = starBtn.dataset.starTitle;
        const issueDate = ISSUES[currentIdx]?.date || "";
        if (starredMap[pid]) {
          delete starredMap[pid];
          starBtn.classList.remove("starred");
          starBtn.textContent = "☆ 收藏";
          showToast("已取消收藏");
        } else {
          starredMap[pid] = { date: issueDate, paper_id: pid, title, verdict: "liked", note: "" };
          starBtn.classList.add("starred");
          starBtn.textContent = "★ 已收藏";
          showToast("已收藏 · 可从页脚导出反馈");
        }
        saveStars();
        // refresh filter count gently
        if (activeFilter === "starred") render();
        else {
          const pill = document.querySelector('button[data-filter="starred"] .cnt');
          if (pill) pill.textContent = Object.keys(starredMap).length;
        }
      }
    });

    document.getElementById("exportStarBtn").addEventListener("click", async () => {
      const vals = Object.values(starredMap);
      if (!vals.length) {
        showToast("还没有收藏的论文");
        return;
      }
      const jsonl = vals.map(v => JSON.stringify(v)).join("\n");
      try {
        await navigator.clipboard.writeText(jsonl);
        showToast(`已复制 ${vals.length} 条记录，可直接粘贴到 profile/feedback.jsonl`);
      } catch {
        prompt("请复制以下 JSONL 到 profile/feedback.jsonl：", jsonl);
      }
    });

    function applyTheme(mode) {
      document.documentElement.setAttribute("data-theme", mode);
      themeBtn.textContent = mode === "dark" ? "浅色" : "深色";
      try { localStorage.setItem(STORAGE_KEY_THEME, mode); } catch {}
    }
    try {
      if (localStorage.getItem(STORAGE_KEY_THEME) === "dark") applyTheme("dark");
    } catch {}
    themeBtn.addEventListener("click", () => {
      const cur = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
      applyTheme(cur === "dark" ? "light" : "dark");
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
