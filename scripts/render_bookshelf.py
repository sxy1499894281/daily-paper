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
      --bg: #f6f4ef;
      --paper: #fcfbf8;
      --paper-inset: #f2efe8;
      --ink: #1d1c1a;
      --ink-2: #4e4b45;
      --ink-muted: #8a847b;
      --rule: #e4dfd5;
      --rule-strong: #c9c2b5;
      --accent: #2c4654;
      --accent-soft: rgba(44, 70, 84, 0.08);
      --seal: #9e3b33;
      --seal-soft: rgba(158, 59, 51, 0.08);
      --warm: #9a6534;
      --warm-soft: rgba(154, 101, 52, 0.09);
      --caution: #8c6239;
      --caution-bg: rgba(140, 98, 57, 0.08);
      --serif: "Iowan Old Style", "Palatino Linotype", "Source Serif 4", "Songti SC", "STSong", "Noto Serif SC", Georgia, serif;
      --sans: -apple-system, BlinkMacSystemFont, "Inter", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", sans-serif;
      --mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
    }
    [data-theme="dark"] {
      --bg: #141413;
      --paper: #1b1a18;
      --paper-inset: #22211e;
      --ink: #eae6de;
      --ink-2: #bab4a8;
      --ink-muted: #857f74;
      --rule: #2b2925;
      --rule-strong: #3e3b35;
      --accent: #9bb8c7;
      --accent-soft: rgba(155, 184, 199, 0.11);
      --seal: #d4766b;
      --seal-soft: rgba(212, 118, 107, 0.12);
      --warm: #d4a36e;
      --warm-soft: rgba(212, 163, 110, 0.12);
      --caution: #cfa270;
      --caution-bg: rgba(207, 162, 112, 0.1);
    }

    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: var(--sans);
      font-size: 15px;
      line-height: 1.7;
      -webkit-font-smoothing: antialiased;
      background-image: radial-gradient(circle at 18% 0%, rgba(158, 59, 51, 0.028), transparent 42%),
                        radial-gradient(circle at 85% 15%, rgba(44, 70, 84, 0.03), transparent 45%);
    }

    .progress-rail {
      position: fixed;
      top: 0; left: 0; right: 0;
      height: 2px;
      background: transparent;
      z-index: 100;
      pointer-events: none;
    }
    .progress-bar {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent), var(--seal));
      transition: width 0.08s linear;
    }

    a {
      color: var(--ink);
      text-decoration: none;
      transition: color 0.16s ease, border-color 0.16s ease;
    }
    a:hover { color: var(--accent); }

    .page-shell {
      max-width: 1120px;
      margin: 0 auto;
      padding: 28px 24px 80px;
    }

    /* Editorial Masthead */
    .masthead {
      border-top: 2px solid var(--ink);
      border-bottom: 1px solid var(--rule-strong);
      padding: 22px 0 18px;
      position: relative;
    }
    .masthead::before {
      content: "";
      display: block;
      position: absolute;
      top: 3px; left: 0; right: 0;
      border-top: 1px solid var(--rule);
    }
    .masthead-top {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      justify-content: space-between;
      gap: 16px;
    }
    .title-group {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .seal-mark {
      width: 34px;
      height: 34px;
      border: 1.5px solid var(--seal);
      border-radius: 4px;
      color: var(--seal);
      font-family: var(--serif);
      font-size: 13px;
      font-weight: 700;
      line-height: 1.05;
      display: grid;
      place-items: center;
      letter-spacing: 0.06em;
      flex-shrink: 0;
      background: var(--seal-soft);
      user-select: none;
    }
    .brand-eyebrow {
      font-family: var(--mono);
      font-size: 11px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--ink-muted);
      margin-bottom: 2px;
    }
    .brand-title {
      margin: 0;
      font-family: var(--serif);
      font-size: 1.72rem;
      font-weight: 600;
      letter-spacing: 0.01em;
      line-height: 1.18;
    }
    .brand-sub {
      margin: 6px 0 0;
      font-size: 0.85rem;
      color: var(--ink-muted);
      font-family: var(--mono);
    }
    .masthead-controls {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }
    .ctrl-btn, .ctrl-select {
      font-family: var(--sans);
      font-size: 0.83rem;
      color: var(--ink-2);
      background: var(--paper);
      border: 1px solid var(--rule-strong);
      border-radius: 6px;
      padding: 6px 11px;
      cursor: pointer;
      transition: all 0.16s ease;
    }
    .ctrl-btn:hover, .ctrl-select:hover {
      border-color: var(--ink);
      color: var(--ink);
    }
    .ctrl-select { font-family: var(--mono); font-size: 0.8rem; }

    /* Lead Pick */
    .lead-feature {
      margin-top: 24px;
      padding: 20px 24px;
      background: var(--paper);
      border: 1px solid var(--rule);
      border-radius: 4px;
      position: relative;
    }
    .lead-feature::before {
      content: "";
      position: absolute;
      left: 0; top: 14px; bottom: 14px;
      width: 2.5px;
      background: var(--seal);
    }
    .lead-kicker {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      font-family: var(--mono);
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--seal);
      margin-bottom: 7px;
    }
    .lead-kicker .sep { color: var(--rule-strong); }
    .lead-kicker .ref { color: var(--ink-muted); letter-spacing: 0.04em; text-transform: none; }
    .lead-heading {
      margin: 0 0 7px;
      font-family: var(--serif);
      font-size: 1.3rem;
      font-weight: 600;
      line-height: 1.35;
    }
    .lead-heading a { border-bottom: 1px solid transparent; }
    .lead-heading a:hover { color: var(--ink); border-bottom-color: var(--seal); }
    .lead-body {
      margin: 0;
      color: var(--ink-2);
      font-size: 0.93rem;
      max-width: 84ch;
    }

    /* Hot Fresh Pulse Strip */
    .hot-pulse {
      margin-top: 12px;
      padding: 9px 14px;
      background: var(--paper-inset);
      border: 1px solid var(--rule);
      border-radius: 4px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px 14px;
      font-size: 0.82rem;
    }
    .hot-pulse-label {
      font-family: var(--mono);
      font-size: 0.72rem;
      letter-spacing: 0.08em;
      color: var(--ink-muted);
      text-transform: uppercase;
      white-space: nowrap;
    }
    .hot-pulse-items {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 14px;
      align-items: center;
    }
    .hot-chip {
      display: inline-flex;
      align-items: baseline;
      gap: 6px;
      color: var(--ink-2);
      font-size: 0.82rem;
    }
    .hot-chip:hover { color: var(--seal); }
    .hot-chip-score {
      font-family: var(--mono);
      font-size: 0.74rem;
      font-weight: 600;
      color: var(--seal);
    }

    /* Understated Filter, Sort & Search Strip */
    .filter-bar {
      margin-top: 22px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--rule);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .filter-tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 4px 15px;
    }
    .filter-tab {
      background: none;
      border: none;
      padding: 4px 0;
      font: inherit;
      font-size: 0.85rem;
      color: var(--ink-muted);
      cursor: pointer;
      position: relative;
      transition: color 0.15s ease;
    }
    .filter-tab:hover { color: var(--ink); }
    .filter-tab.active {
      color: var(--ink);
      font-weight: 600;
    }
    .filter-tab.active::after {
      content: "";
      position: absolute;
      left: 0; right: 0; bottom: -2px;
      height: 1.5px;
      background: var(--ink);
    }
    .filter-tab .tab-cnt {
      font-family: var(--mono);
      font-size: 0.74rem;
      color: var(--ink-muted);
      margin-left: 4px;
    }
    .filter-right {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
    }
    .sort-group {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 0.78rem;
      color: var(--ink-muted);
      font-family: var(--mono);
    }
    .sort-btn {
      background: none;
      border: 1px solid transparent;
      border-radius: 4px;
      padding: 2px 7px;
      font-family: var(--sans);
      font-size: 0.79rem;
      color: var(--ink-muted);
      cursor: pointer;
    }
    .sort-btn:hover { color: var(--ink); }
    .sort-btn.active {
      color: var(--ink);
      background: var(--paper);
      border-color: var(--rule-strong);
      font-weight: 500;
    }
    .search-wrap {
      display: flex;
      align-items: center;
      border-bottom: 1px solid var(--rule-strong);
      padding-bottom: 2px;
      min-width: 190px;
      transition: border-color 0.16s ease;
    }
    .search-wrap:focus-within { border-bottom-color: var(--ink); }
    .search-input {
      border: none;
      background: transparent;
      color: var(--ink);
      font: inherit;
      font-size: 0.85rem;
      width: 100%;
      outline: none;
      padding: 2px 4px;
    }
    .search-input::placeholder { color: var(--ink-muted); }

    /* Two-column editorial workspace */
    .workspace {
      display: grid;
      grid-template-columns: 204px minmax(0, 1fr);
      gap: 44px;
      margin-top: 26px;
      align-items: start;
    }

    /* Sticky Topic Spine */
    aside.spine {
      position: sticky;
      top: 24px;
      padding-right: 12px;
    }
    .spine-label {
      font-family: var(--mono);
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--ink-muted);
      margin: 0 0 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--rule);
    }
    .spine-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .spine-link {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 8px;
      padding: 6px 8px;
      border-radius: 4px;
      font-size: 0.87rem;
      color: var(--ink-2);
      border-left: 2px solid transparent;
    }
    .spine-link:hover { background: var(--paper); color: var(--ink); }
    .spine-link.current {
      color: var(--ink);
      font-weight: 600;
      border-left-color: var(--seal);
      background: var(--paper);
    }
    .spine-left { display: flex; align-items: baseline; gap: 7px; min-width: 0; }
    .spine-num { font-family: var(--mono); font-size: 0.72rem; color: var(--ink-muted); }
    .spine-tier-dot {
      width: 5px; height: 5px; border-radius: 50%;
      background: var(--accent); display: inline-block;
      transform: translateY(-1px); flex-shrink: 0;
    }
    .spine-cnt { font-family: var(--mono); font-size: 0.74rem; color: var(--ink-muted); }
    .spine-legend {
      margin-top: 16px;
      padding-top: 12px;
      border-top: 1px solid var(--rule);
      font-size: 0.75rem;
      color: var(--ink-muted);
      line-height: 1.75;
    }
    .legend-pips {
      display: inline-flex;
      gap: 3px;
      vertical-align: middle;
      margin-right: 4px;
    }

    .mobile-topics {
      display: none;
      overflow-x: auto;
      gap: 8px;
      padding: 10px 0;
      margin-top: 12px;
      border-bottom: 1px solid var(--rule);
      position: sticky;
      top: 0;
      background: var(--bg);
      z-index: 20;
    }
    .mobile-topics a {
      white-space: nowrap;
      font-size: 0.82rem;
      padding: 4px 10px;
      border: 1px solid var(--rule-strong);
      border-radius: 999px;
      background: var(--paper);
      color: var(--ink-2);
    }

    /* Topic Sections */
    section.topic-section {
      margin-bottom: 46px;
      scroll-margin-top: 28px;
    }
    .topic-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--ink);
      margin-bottom: 6px;
    }
    .topic-head-left { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
    .topic-index { font-family: var(--mono); font-size: 0.8rem; color: var(--ink-muted); }
    .topic-name {
      margin: 0;
      font-family: var(--serif);
      font-size: 1.36rem;
      font-weight: 600;
      letter-spacing: 0.01em;
    }
    .topic-tier {
      font-family: var(--mono);
      font-size: 0.72rem;
      letter-spacing: 0.06em;
      color: var(--ink-muted);
      text-transform: uppercase;
    }
    .topic-tier.is-t1 { color: var(--accent); }
    .topic-count { font-family: var(--mono); font-size: 0.78rem; color: var(--ink-muted); }
    .topic-note {
      margin: 10px 0 4px;
      padding: 9px 13px;
      background: var(--paper-inset);
      border-radius: 4px;
      font-size: 0.85rem;
      color: var(--ink-2);
    }

    /* Editorial Paper Entry */
    article.entry {
      padding: 20px 0;
      border-bottom: 1px solid var(--rule);
      scroll-margin-top: 32px;
    }
    article.entry:last-child { border-bottom-color: var(--rule-strong); }

    .entry-eyebrow {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 7px;
      font-family: var(--mono);
      font-size: 0.76rem;
      color: var(--ink-muted);
    }
    .eyebrow-left {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }
    .tier-indicator {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-family: var(--sans);
      font-size: 0.76rem;
      font-weight: 500;
      color: var(--ink-2);
    }
    .tier-indicator.deep::before {
      content: "";
      width: 6px; height: 6px; border-radius: 50%;
      background: var(--seal);
    }
    .tier-indicator.scan::before {
      content: "";
      width: 6px; height: 6px; border-radius: 50%;
      border: 1.5px solid var(--accent);
    }
    .lane-mark {
      font-family: var(--sans);
      font-size: 0.73rem;
      color: var(--seal);
      background: var(--seal-soft);
      padding: 1px 7px;
      border-radius: 3px;
    }
    .dir-mark {
      font-family: var(--mono);
      font-size: 0.72rem;
      color: var(--accent);
      background: var(--accent-soft);
      padding: 1px 7px;
      border-radius: 3px;
    }

    /* Refined Heat Micro-Widget */
    .eyebrow-right {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .heat-widget {
      position: relative;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 3px 9px;
      border-radius: 4px;
      background: var(--paper);
      border: 1px solid var(--rule);
      font-family: var(--mono);
      font-size: 0.74rem;
      color: var(--ink-2);
    }
    .heat-widget.is-hot {
      border-color: rgba(158, 59, 51, 0.3);
      background: var(--seal-soft);
    }
    .heat-widget.is-warm {
      border-color: rgba(154, 101, 52, 0.28);
      background: var(--warm-soft);
    }
    .heat-widget.is-cold {
      background: transparent;
      border-style: dashed;
      color: var(--ink-muted);
    }
    .heat-score-num {
      font-weight: 700;
      letter-spacing: -0.01em;
    }
    .heat-widget.is-hot .heat-score-num { color: var(--seal); }
    .heat-widget.is-warm .heat-score-num { color: var(--warm); }
    .heat-pips {
      display: inline-flex;
      align-items: center;
      gap: 3px;
    }
    .pip {
      width: 5px;
      height: 5px;
      border-radius: 50%;
      border: 1px solid var(--rule-strong);
      display: inline-block;
    }
    .pip.on-cit { background: var(--ink-2); border-color: var(--ink-2); }
    .pip.on-comm { background: var(--seal); border-color: var(--seal); }
    .pip.on-star { background: var(--accent); border-color: var(--accent); }
    .heat-dims {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding-left: 7px;
      border-left: 1px solid var(--rule);
      font-size: 0.72rem;
      color: var(--ink-muted);
    }
    .heat-dim-link {
      color: var(--ink-2);
      white-space: nowrap;
    }
    .heat-dim-link:hover {
      color: var(--seal);
      text-decoration: underline;
    }
    .heat-dim-link .k {
      color: var(--ink-muted);
      margin-right: 2px;
      font-family: var(--sans);
      font-size: 0.7rem;
    }

    /* Subtle hover tooltip on heat widget */
    .heat-popover {
      position: absolute;
      right: 0;
      top: calc(100% + 6px);
      width: 248px;
      padding: 10px 12px;
      background: var(--paper);
      border: 1px solid var(--rule-strong);
      border-radius: 5px;
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
      font-family: var(--sans);
      font-size: 0.76rem;
      color: var(--ink-2);
      line-height: 1.55;
      opacity: 0;
      visibility: hidden;
      transform: translateY(4px);
      transition: opacity 0.14s ease, transform 0.14s ease, visibility 0.14s ease;
      z-index: 30;
      pointer-events: none;
    }
    .heat-widget:hover .heat-popover {
      opacity: 1;
      visibility: visible;
      transform: translateY(0);
    }
    .pop-head {
      display: flex;
      justify-content: space-between;
      font-family: var(--mono);
      font-size: 0.72rem;
      color: var(--ink-muted);
      padding-bottom: 5px;
      margin-bottom: 6px;
      border-bottom: 1px solid var(--rule);
    }
    .pop-row {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 2px;
    }
    .pop-row .v { font-family: var(--mono); color: var(--ink); }
    .pop-row .miss { font-style: italic; color: var(--ink-muted); }

    .star-btn {
      background: none;
      border: none;
      padding: 2px 4px;
      cursor: pointer;
      font-size: 1rem;
      line-height: 1;
      color: var(--ink-muted);
      transition: transform 0.15s ease, color 0.15s ease;
    }
    .star-btn:hover { color: var(--seal); transform: scale(1.12); }
    .star-btn.starred { color: var(--seal); }

    .entry-title {
      margin: 0;
      font-family: var(--serif);
      font-size: 1.15rem;
      font-weight: 600;
      line-height: 1.42;
      letter-spacing: 0.005em;
    }
    .entry-title a { border-bottom: 1px solid transparent; }
    .entry-title a:hover { color: var(--ink); border-bottom-color: var(--ink-muted); }
    .entry-authors { margin: 3px 0 0; font-size: 0.81rem; color: var(--ink-muted); }
    .entry-intro {
      margin: 10px 0 11px;
      font-size: 0.95rem;
      color: var(--ink);
      line-height: 1.72;
    }

    .entry-foot {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px 14px;
    }
    .tag-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
    .micro-tag {
      font-family: var(--mono);
      font-size: 0.72rem;
      color: var(--ink-muted);
      border: 1px solid var(--rule);
      background: var(--paper);
      padding: 1px 7px;
      border-radius: 3px;
    }
    .micro-tag.caution {
      color: var(--caution);
      background: var(--caution-bg);
      border-color: transparent;
    }
    .micro-tag.sec-link { border-style: dashed; }

    .entry-actions {
      display: flex;
      align-items: center;
      gap: 14px;
      font-size: 0.81rem;
      color: var(--ink-muted);
    }
    .entry-actions a {
      color: var(--ink-2);
      border-bottom: 1px solid var(--rule-strong);
      padding-bottom: 1px;
    }
    .entry-actions a:hover { color: var(--accent); border-bottom-color: var(--accent); }

    /* Expandable Deep-Read Drawer */
    details.drawer { margin-top: 10px; }
    details.drawer summary {
      list-style: none;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 0.82rem;
      color: var(--accent);
      font-weight: 500;
      user-select: none;
      padding: 2px 0;
    }
    details.drawer summary::-webkit-details-marker { display: none; }
    details.drawer summary::before {
      content: "＋";
      font-family: var(--mono);
      font-size: 0.8rem;
      color: var(--ink-muted);
    }
    details.drawer[open] summary::before { content: "－"; }

    .drawer-body {
      margin-top: 12px;
      padding: 18px 20px;
      background: var(--paper);
      border: 1px solid var(--rule);
      border-radius: 4px;
      display: grid;
      gap: 15px;
    }
    .detail-item {
      display: grid;
      grid-template-columns: 78px minmax(0, 1fr);
      gap: 14px;
      align-items: baseline;
    }
    .detail-label {
      font-size: 0.78rem;
      font-weight: 600;
      color: var(--ink-muted);
      letter-spacing: 0.04em;
    }
    .detail-val {
      font-size: 0.9rem;
      color: var(--ink-2);
      line-height: 1.75;
      margin: 0;
    }
    .detail-val ul { margin: 0; padding-left: 18px; }
    .detail-val li { margin-bottom: 3px; }
    .detail-val a { color: var(--accent); border-bottom: 1px solid var(--rule-strong); }

    /* 3-Column Heat Ledger inside Drawer */
    .heat-ledger {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .ledger-cell {
      padding: 10px 12px;
      background: var(--paper-inset);
      border: 1px solid var(--rule);
      border-radius: 4px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .ledger-cell.is-missing {
      background: transparent;
      border-style: dashed;
      opacity: 0.72;
    }
    .ledger-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.74rem;
      color: var(--ink-muted);
    }
    .ledger-weight {
      font-family: var(--mono);
      font-size: 0.69rem;
      color: var(--ink-muted);
    }
    .ledger-num-row {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 6px;
    }
    .ledger-num {
      font-family: var(--mono);
      font-size: 1.08rem;
      font-weight: 600;
      color: var(--ink);
    }
    .ledger-cell.is-missing .ledger-num {
      font-family: var(--sans);
      font-size: 0.84rem;
      font-weight: 400;
      color: var(--ink-muted);
    }
    .ledger-contrib {
      font-family: var(--mono);
      font-size: 0.74rem;
      color: var(--accent);
    }
    .ledger-src {
      font-size: 0.73rem;
      color: var(--ink-muted);
      display: flex;
      justify-content: space-between;
      gap: 6px;
      flex-wrap: wrap;
    }
    .ledger-src a {
      color: var(--accent);
      border-bottom: 1px solid var(--rule-strong);
    }
    .ledger-foot {
      margin-top: 8px;
      font-size: 0.76rem;
      color: var(--ink-muted);
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 6px;
    }
    .ledger-foot strong { font-family: var(--mono); color: var(--ink-2); }

    .empty-state {
      padding: 20px 0;
      color: var(--ink-muted);
      font-size: 0.9rem;
      font-style: italic;
    }

    footer.colophon {
      margin-top: 48px;
      padding-top: 18px;
      border-top: 1px solid var(--rule-strong);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      font-size: 0.8rem;
      color: var(--ink-muted);
    }
    .colophon-actions { display: flex; align-items: center; gap: 10px; }

    .toast {
      position: fixed;
      bottom: 22px;
      right: 22px;
      background: var(--ink);
      color: var(--bg);
      padding: 9px 15px;
      border-radius: 6px;
      font-size: 0.84rem;
      opacity: 0;
      transform: translateY(8px);
      pointer-events: none;
      transition: opacity 0.2s ease, transform 0.2s ease;
      z-index: 200;
    }
    .toast.show { opacity: 1; transform: translateY(0); }

    @media (max-width: 860px) {
      .workspace { grid-template-columns: 1fr; gap: 0; }
      aside.spine { display: none; }
      .mobile-topics { display: flex; }
      .detail-item { grid-template-columns: 1fr; gap: 4px; }
      .heat-ledger { grid-template-columns: 1fr; }
      .heat-popover { display: none; }
      .lead-feature { padding: 18px; }
      .page-shell { padding: 18px 16px 64px; }
    }
  </style>
</head>
<body>
  <div class="progress-rail"><div class="progress-bar" id="progressBar"></div></div>

  <div class="page-shell">
    <header class="masthead">
      <div class="masthead-top">
        <div class="title-group">
          <div class="seal-mark" title="每日论文研选">研选</div>
          <div>
            <div class="brand-eyebrow" id="issueEyebrow">DAILY PAPER ARCHIVE</div>
            <h1 class="brand-title">每日论文书架</h1>
            <p class="brand-sub" id="subtitle">宽进严标 · 导读优先</p>
          </div>
        </div>
        <div class="masthead-controls">
          <select class="ctrl-select" id="dateSelect" aria-label="选择期号"></select>
          <button class="ctrl-btn" id="toggleExpandBtn" type="button">展开全部细读</button>
          <button class="ctrl-btn" id="themeBtn" type="button">松烟深色</button>
        </div>
      </div>
    </header>

    <div id="leadContainer"></div>
    <div id="hotPulseContainer"></div>

    <div class="filter-bar">
      <div class="filter-tabs" id="filterPills">
        <button class="filter-tab active" data-filter="all">全部</button>
        <button class="filter-tab" data-filter="deep">深度精读</button>
        <button class="filter-tab" data-filter="scan">新作速览</button>
        <button class="filter-tab" data-filter="tier1">Tier 1 主线</button>
        <button class="filter-tab" data-filter="open">含开源</button>
        <button class="filter-tab" data-filter="online-rl">在线 RL</button>
        <button class="filter-tab" data-filter="backlist">高热老作</button>
        <button class="filter-tab" data-filter="starred">★ 收藏<span class="tab-cnt" id="starCnt">0</span></button>
      </div>
      <div class="filter-right">
        <div class="sort-group" id="sortGroup">
          <span>排序</span>
          <button class="sort-btn active" data-sort="default" type="button">默认</button>
          <button class="sort-btn" data-sort="heat" type="button">热度 ↓</button>
          <button class="sort-btn" data-sort="date" type="button">最新 ↓</button>
        </div>
        <div class="search-wrap">
          <input class="search-input" id="searchInput" type="search" placeholder="检索标题、导读、标签..." />
        </div>
      </div>
    </div>

    <nav class="mobile-topics" id="mobileTopics"></nav>

    <div class="workspace">
      <aside class="spine">
        <div class="spine-label">栏目索引 · CONTENTS</div>
        <ul class="spine-list" id="spineList"></ul>
        <div class="spine-legend">
          <div><span class="spine-tier-dot"></span> Tier 1 核心主线</div>
          <div><span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--seal);margin-right:4px;"></span>实心点：深度精读</div>
          <div><span style="display:inline-block;width:6px;height:6px;border-radius:50%;border:1.5px solid var(--accent);margin-right:4px;"></span>空心圈：新作速览</div>
          <div style="margin-top:6px;">
            <span class="legend-pips">
              <span class="pip on-cit" title="学术引用"></span>
              <span class="pip on-comm" title="社区讨论"></span>
              <span class="pip on-star" title="仓库星标"></span>
            </span>热度三维覆盖（引/社/星）
          </div>
        </div>
      </aside>
      <main id="content"></main>
    </div>

    <footer class="colophon">
      <span id="statsFooter"></span>
      <div class="colophon-actions">
        <button class="ctrl-btn" id="exportStarBtn" type="button" title="将已点星收藏的论文复制为 feedback.jsonl 格式">复制收藏反馈 JSONL</button>
        <span>Daily Paper Skill · Heat v1</span>
      </div>
    </footer>
  </div>

  <div class="toast" id="toast"></div>

  <script id="issues-data" type="application/json">__ISSUES_JSON__</script>
  <script>
    const ISSUES = JSON.parse(document.getElementById("issues-data").textContent);
    const LANE_LABELS = {
      fresh: "近期新作",
      popular_backlist: "高热老作",
      award: "顶会获奖",
      supplement: "专题补读",
    };
    const STORAGE_KEY_STARS = "daily_paper_starred_v1";
    const STORAGE_KEY_THEME = "daily_paper_theme_v1";

    let currentIdx = 0;
    let activeFilter = "all";
    let activeSort = "default";
    let searchQuery = "";
    let allExpanded = false;
    let starredMap = {};
    try { starredMap = JSON.parse(localStorage.getItem(STORAGE_KEY_STARS) || "{}"); } catch {}

    const dateSelect = document.getElementById("dateSelect");
    const themeBtn = document.getElementById("themeBtn");
    const toggleExpandBtn = document.getElementById("toggleExpandBtn");
    const searchInput = document.getElementById("searchInput");
    const progressBar = document.getElementById("progressBar");
    const toastEl = document.getElementById("toast");

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

    function fmtNum(n) {
      if (n >= 10000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
      if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
      return String(n);
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
      let commContrib = null;
      let primaryCommSig = null;
      if (voteSig || commSig) {
        const vScore = voteSig ? voteSig.count : 0;
        const cScore = commSig ? commSig.count * 2 : 0;
        if (cScore > vScore && commSig) {
          commContrib = cScore;
          primaryCommSig = commSig;
        } else {
          commContrib = vScore;
          primaryCommSig = voteSig || commSig;
        }
      }
      const starContrib = starSig ? starSig.count * 0.1 : null;

      let cov = 0;
      let rawTotal = 0;
      if (citContrib !== null) { rawTotal += citContrib; cov++; }
      if (commContrib !== null) { rawTotal += commContrib; cov++; }
      if (starContrib !== null) { rawTotal += starContrib; cov++; }

      const score = cov > 0 ? Math.round(rawTotal) : null;
      return {
        score,
        coverage: cov,
        citSig, voteSig, commSig, primaryCommSig, starSig,
        citContrib, commContrib, starContrib,
        unavailable: heat?.unavailable || "",
      };
    }

    function renderHeatWidget(paper) {
      const h = analyzeHeat(paper.heat);
      if (h.score === null) {
        return `
          <div class="heat-widget is-cold" title="${esc(h.unavailable || "暂无可核验外部热度")}">
            <span>新作冷启动</span>
            <span class="heat-pips">
              <span class="pip"></span><span class="pip"></span><span class="pip"></span>
            </span>
            <div class="heat-popover">
              <div class="pop-head"><span>Heat v1</span><span>覆盖 0/3</span></div>
              <div>${esc(h.unavailable || "近期刚发布，OpenAlex / HF Papers / GitHub 暂未收录外部记录。请结合导读与标签判断。")}</div>
            </div>
          </div>`;
      }

      const heatClass = h.score >= 50 ? "is-hot" : (h.score >= 10 ? "is-warm" : "");
      const dimParts = [];
      if (h.citSig) {
        dimParts.push(`<a class="heat-dim-link" href="${esc(h.citSig.url)}" target="_blank" rel="noopener" title="OpenAlex / 学术引用"><span class="k">引</span>${fmtNum(h.citSig.count)}</a>`);
      }
      if (h.primaryCommSig) {
        const unit = h.primaryCommSig.kind === "comments" ? "评" : "票";
        dimParts.push(`<a class="heat-dim-link" href="${esc(h.primaryCommSig.url)}" target="_blank" rel="noopener" title="${esc(h.primaryCommSig.source)}"><span class="k">${unit}</span>${fmtNum(h.primaryCommSig.count)}</a>`);
      }
      if (h.starSig) {
        dimParts.push(`<a class="heat-dim-link" href="${esc(h.starSig.url)}" target="_blank" rel="noopener" title="GitHub 官方仓库星标"><span class="k">星</span>${fmtNum(h.starSig.count)}</a>`);
      }

      const popCit = h.citSig
        ? `<span class="v">${h.citSig.count} × 3 = ${h.citContrib}</span>`
        : `<span class="miss">缺项（不计 0）</span>`;
      const popComm = h.primaryCommSig
        ? `<span class="v">${h.voteSig ? h.voteSig.count + "票" : ""}${h.voteSig && h.commSig ? " / " : ""}${h.commSig ? h.commSig.count + "评" : ""} → ${h.commContrib}</span>`
        : `<span class="miss">缺项（不计 0）</span>`;
      const popStar = h.starSig
        ? `<span class="v">${h.starSig.count} × 0.1 = ${h.starContrib.toFixed(1)}</span>`
        : `<span class="miss">缺项（不计 0）</span>`;

      return `
        <div class="heat-widget ${heatClass}">
          <span class="heat-score-num">${fmtNum(h.score)}</span>
          <span class="heat-pips" aria-label="覆盖度 ${h.coverage}/3">
            <span class="pip ${h.citSig ? "on-cit" : ""}"></span>
            <span class="pip ${h.primaryCommSig ? "on-comm" : ""}"></span>
            <span class="pip ${h.starSig ? "on-star" : ""}"></span>
          </span>
          ${dimParts.length ? `<span class="heat-dims">${dimParts.join("")}</span>` : ""}
          <div class="heat-popover">
            <div class="pop-head"><span>热度指数 ${h.score}</span><span>覆盖 ${h.coverage}/3</span></div>
            <div class="pop-row"><span>学术引用</span>${popCit}</div>
            <div class="pop-row"><span>社区讨论</span>${popComm}</div>
            <div class="pop-row"><span>仓库关注</span>${popStar}</div>
          </div>
        </div>`;
    }

    function renderHeatLedger(paper) {
      const h = analyzeHeat(paper.heat);
      if (h.score === null) {
        return `
          <div class="detail-val">
            <div class="heat-ledger">
              <div class="ledger-cell is-missing"><div class="ledger-top"><span>学术引用</span><span class="ledger-weight">× 3</span></div><div class="ledger-num">暂无记录</div></div>
              <div class="ledger-cell is-missing"><div class="ledger-top"><span>社区讨论</span><span class="ledger-weight">max(票, 评×2)</span></div><div class="ledger-num">暂无记录</div></div>
              <div class="ledger-cell is-missing"><div class="ledger-top"><span>仓库关注</span><span class="ledger-weight">× 0.1</span></div><div class="ledger-num">暂无记录</div></div>
            </div>
            <div class="ledger-foot">
              <span>${esc(h.unavailable || "暂无可核验外部热度数据")}</span>
              <span>覆盖度 <strong>0/3</strong></span>
            </div>
          </div>`;
      }

      const citCell = h.citSig ? `
        <div class="ledger-cell">
          <div class="ledger-top"><span>学术引用</span><span class="ledger-weight">× 3</span></div>
          <div class="ledger-num-row">
            <span class="ledger-num">${h.citSig.approximate ? "≈" : ""}${h.citSig.count.toLocaleString()}</span>
            <span class="ledger-contrib">+${h.citContrib}</span>
          </div>
          <div class="ledger-src"><span>${esc(h.citSig.source)} · ${esc(h.citSig.observed_on)}</span><a href="${esc(h.citSig.url)}" target="_blank" rel="noopener">核验 ↗</a></div>
        </div>` : `
        <div class="ledger-cell is-missing">
          <div class="ledger-top"><span>学术引用</span><span class="ledger-weight">× 3</span></div>
          <div class="ledger-num">缺项（不计 0）</div>
        </div>`;

      const commCell = h.primaryCommSig ? `
        <div class="ledger-cell">
          <div class="ledger-top"><span>社区讨论</span><span class="ledger-weight">max(票, 评×2)</span></div>
          <div class="ledger-num-row">
            <span class="ledger-num">${h.voteSig ? h.voteSig.count + " 票" : ""}${h.voteSig && h.commSig ? " · " : ""}${h.commSig ? h.commSig.count + " 评" : ""}</span>
            <span class="ledger-contrib">+${h.commContrib}</span>
          </div>
          <div class="ledger-src"><span>${esc(h.primaryCommSig.source)} · ${esc(h.primaryCommSig.observed_on)}</span><a href="${esc(h.primaryCommSig.url)}" target="_blank" rel="noopener">核验 ↗</a></div>
        </div>` : `
        <div class="ledger-cell is-missing">
          <div class="ledger-top"><span>社区讨论</span><span class="ledger-weight">max(票, 评×2)</span></div>
          <div class="ledger-num">缺项（不计 0）</div>
        </div>`;

      const starCell = h.starSig ? `
        <div class="ledger-cell">
          <div class="ledger-top"><span>仓库关注</span><span class="ledger-weight">× 0.1</span></div>
          <div class="ledger-num-row">
            <span class="ledger-num">${h.starSig.count.toLocaleString()} ★</span>
            <span class="ledger-contrib">+${h.starContrib.toFixed(1)}</span>
          </div>
          <div class="ledger-src"><span>${esc(h.starSig.source)} · ${esc(h.starSig.observed_on)}</span><a href="${esc(h.starSig.url)}" target="_blank" rel="noopener">核验 ↗</a></div>
        </div>` : `
        <div class="ledger-cell is-missing">
          <div class="ledger-top"><span>仓库关注</span><span class="ledger-weight">× 0.1</span></div>
          <div class="ledger-num">缺项（不计 0）</div>
        </div>`;

      return `
        <div class="detail-val">
          <div class="heat-ledger">${citCell}${commCell}${starCell}</div>
          <div class="ledger-foot">
            <span>综合指数 <strong>${h.score}</strong> · 覆盖度 <strong>${h.coverage}/3</strong></span>
            <span>仅反映外部关注度，近期新作常处冷启动期，不代表研究质量排序</span>
          </div>
        </div>`;
    }

    function saveStars() {
      try { localStorage.setItem(STORAGE_KEY_STARS, JSON.stringify(starredMap)); } catch {}
      document.getElementById("starCnt").textContent = Object.keys(starredMap).length;
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
      if (activeFilter === "starred" && !starredMap[paper.id]) return false;
      if (searchQuery) {
        const hay = [
          paper.title, paper.intro, paper.abstract_zh, paper.method, paper.results,
          paper.authors_or_org, ...(tags), ...(paper.directions || []), ...(paper.secondary_topics || [])
        ].join(" ").toLowerCase();
        if (!hay.includes(searchQuery)) return false;
      }
      return true;
    }

    function sortPapers(papers) {
      if (activeSort === "default") return papers;
      const copy = [...papers];
      if (activeSort === "heat") {
        copy.sort((a, b) => {
          const ha = analyzeHeat(a.heat);
          const hb = analyzeHeat(b.heat);
          const sa = ha.score === null ? -1 : ha.score;
          const sb = hb.score === null ? -1 : hb.score;
          return sb - sa || hb.coverage - ha.coverage;
        });
      } else if (activeSort === "date") {
        copy.sort((a, b) => String(b.published_on || "").localeCompare(String(a.published_on || "")));
      }
      return copy;
    }

    let spyObserver = null;
    function setupScrollSpy() {
      if (spyObserver) spyObserver.disconnect();
      const links = new Map();
      document.querySelectorAll(".spine-link").forEach(a => {
        const id = a.getAttribute("href").slice(1);
        links.set(id, a);
      });
      spyObserver = new IntersectionObserver((entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            links.forEach(el => el.classList.remove("current"));
            const active = links.get(entry.target.id);
            if (active) active.classList.add("current");
          }
        }
      }, { rootMargin: "-12% 0px -72% 0px", threshold: 0 });
      document.querySelectorAll("section.topic-section").forEach(sec => spyObserver.observe(sec));
    }

    function shortTitle(title) {
      const colon = title.indexOf(":");
      if (colon > 2 && colon <= 34) return title.slice(0, colon);
      return title.length > 34 ? title.slice(0, 33) + "…" : title;
    }

    function render() {
      const issue = ISSUES[currentIdx];
      if (!issue) return;

      const allPapers = [];
      for (const sec of issue.sections) {
        for (const p of sec.papers) allPapers.push({ paper: p, sec });
      }
      const deepCnt = allPapers.filter(x => (x.paper.reading_tier || "deep") === "deep").length;
      const scanCnt = allPapers.length - deepCnt;
      const leadObj = allPapers.find(x => x.paper.id === issue.lead.paper_id);

      document.getElementById("issueEyebrow").textContent =
        `ISSUE ${issue.date.replace(/-/g, ".")} · ${issue.timezone.toUpperCase()}`;
      document.getElementById("subtitle").textContent =
        `收录 ${allPapers.length} 篇（精读 ${deepCnt} · 速览 ${scanCnt}） · 宽进严标，导读优先`;
      document.getElementById("starCnt").textContent = Object.keys(starredMap).length;

      document.getElementById("leadContainer").innerHTML = `
        <section class="lead-feature">
          <div class="lead-kicker">
            <span>卷首首推 · EDITOR'S LEAD</span>
            ${issue.lead.section_ref ? `<span class="sep">/</span><span class="ref">${esc(issue.lead.section_ref)}</span>` : ""}
          </div>
          <h2 class="lead-heading">
            ${leadObj ? `<a href="${esc(leadObj.paper.url)}" target="_blank" rel="noopener">${esc(leadObj.paper.title)}</a>` : esc(issue.lead.paper_id)}
          </h2>
          <p class="lead-body">${esc(issue.lead.reason)}</p>
        </section>`;

      // Top fresh papers by verified heat for quick pulse navigation
      const hotFresh = allPapers
        .filter(x => x.paper.lane === "fresh")
        .map(x => ({ paper: x.paper, h: analyzeHeat(x.paper.heat) }))
        .filter(x => x.h.score !== null && x.h.score > 0)
        .sort((a, b) => b.h.score - a.h.score)
        .slice(0, 4);

      const pulseEl = document.getElementById("hotPulseContainer");
      if (hotFresh.length) {
        pulseEl.innerHTML = `
          <div class="hot-pulse">
            <span class="hot-pulse-label">近期新作热度速览</span>
            <div class="hot-pulse-items">
              ${hotFresh.map(x => `
                <a class="hot-chip" href="#paper-${esc(x.paper.id)}">
                  <span>${esc(shortTitle(x.paper.title))}</span>
                  <span class="hot-chip-score">${x.h.score}</span>
                </a>`).join('<span style="color:var(--rule-strong)">·</span>')}
            </div>
          </div>`;
      } else {
        pulseEl.innerHTML = "";
      }

      const spineParts = [];
      const mobileParts = [];
      const secParts = [];
      let visibleCount = 0;

      issue.sections.forEach((sec, idx) => {
        const filtered = sortPapers(sec.papers.filter(p => matchesFilter(p, sec)));
        visibleCount += filtered.length;
        const num = String(idx + 1).padStart(2, "0");
        const isT1 = sec.priority === "tier1";

        spineParts.push(`
          <li>
            <a class="spine-link ${idx === 0 ? "current" : ""}" href="#topic-${idx}">
              <span class="spine-left">
                <span class="spine-num">${num}</span>
                <span>${esc(sec.topic)}</span>
                ${isT1 ? `<span class="spine-tier-dot" title="Tier 1 核心主线"></span>` : ""}
              </span>
              <span class="spine-cnt">${filtered.length}</span>
            </a>
          </li>`);
        mobileParts.push(`<a href="#topic-${idx}">${num} ${esc(sec.topic)} (${filtered.length})</a>`);

        const noteHtml = sec.note ? `<div class="topic-note">${esc(sec.note)}</div>` : "";
        const cardsHtml = filtered.length ? filtered.map(p => {
          const tier = p.reading_tier || "deep";
          const isStarred = !!starredMap[p.id];

          const dirHtml = (p.directions || []).map(d => `<span class="dir-mark">${esc(d)}</span>`).join("");
          const laneHtml = p.lane !== "fresh" ? `<span class="lane-mark">${esc(LANE_LABELS[p.lane] || p.lane)}</span>` : "";
          const tagHtml = (p.tags || []).map(t => {
            const cls = (t === "offline-only" || t === "no-code-yet") ? "micro-tag caution" : "micro-tag";
            return `<span class="${cls}">${esc(t)}</span>`;
          }).join("");
          const secHtml = (p.secondary_topics || []).map(t => `<span class="micro-tag sec-link">↳ ${esc(t)}</span>`).join("");

          const awardRow = p.award
            ? `<div class="detail-item"><div class="detail-label">官方奖项</div><p class="detail-val">${esc(p.award.venue)} ${p.award.year} · ${esc(p.award.name)}（${esc(p.award.scope)}，不计入热度） · <a href="${esc(p.award.url)}" target="_blank" rel="noopener">记录 ↗</a></p></div>`
            : "";
          const backlistRow = (p.backlist_evidence && p.backlist_evidence.length)
            ? `<div class="detail-item"><div class="detail-label">老作依据</div><div class="detail-val"><ul>${p.backlist_evidence.map(e => `<li>${esc(e.summary)} · <a href="${esc(e.url)}" target="_blank" rel="noopener">核验 ↗</a></li>`).join("")}</ul></div></div>`
            : "";

          return `
            <article class="entry" id="paper-${esc(p.id)}">
              <div class="entry-eyebrow">
                <div class="eyebrow-left">
                  <span class="tier-indicator ${tier}">${tier === "deep" ? "深度精读" : "新作速览"}</span>
                  <span>·</span>
                  <span>${esc(p.published_on)}</span>
                  <span>·</span>
                  <span>${esc(p.id)}</span>
                  ${laneHtml}
                  ${dirHtml}
                </div>
                <div class="eyebrow-right">
                  ${renderHeatWidget(p)}
                  <button class="star-btn ${isStarred ? "starred" : ""}" data-star-id="${esc(p.id)}" data-star-title="${esc(p.title)}" title="${isStarred ? "取消收藏" : "收藏这篇论文"}">${isStarred ? "★" : "☆"}</button>
                </div>
              </div>

              <h3 class="entry-title"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a></h3>
              ${p.authors_or_org ? `<div class="entry-authors">${esc(p.authors_or_org)}</div>` : ""}
              <p class="entry-intro">${esc(p.intro)}</p>
              ${p.revision_note ? `<div class="topic-note">版本修订：${esc(p.revision_note)}</div>` : ""}

              <div class="entry-foot">
                <div class="tag-row">${tagHtml}${secHtml}</div>
                <div class="entry-actions">
                  <a href="${esc(p.url)}" target="_blank" rel="noopener">原文 ↗</a>
                  ${p.repo_url ? `<a href="${esc(p.repo_url)}" target="_blank" rel="noopener">代码 ↗</a>` : ""}
                </div>
              </div>

              <details class="drawer" ${allExpanded ? "open" : ""}>
                <summary>展开细读（摘要译述 · 方法 · 实验 · 局限 · 热度账本）</summary>
                <div class="drawer-body">
                  <div class="detail-item"><div class="detail-label">摘要译述</div><p class="detail-val">${esc(p.abstract_zh)}</p></div>
                  <div class="detail-item"><div class="detail-label">方法论</div><p class="detail-val">${esc(p.method)}</p></div>
                  <div class="detail-item"><div class="detail-label">实验结果</div><p class="detail-val">${esc(p.results)}</p></div>
                  <div class="detail-item"><div class="detail-label">关键局限</div><p class="detail-val">${esc(p.limitation)}</p></div>
                  <div class="detail-item"><div class="detail-label">热度账本</div>${renderHeatLedger(p)}</div>
                  ${awardRow}
                  ${backlistRow}
                </div>
              </details>
            </article>`;
        }).join("") : `<div class="empty-state">当前筛选条件下本栏暂无条目。</div>`;

        secParts.push(`
          <section class="topic-section" id="topic-${idx}">
            <div class="topic-head">
              <div class="topic-head-left">
                <span class="topic-index">${num}</span>
                <h2 class="topic-name">${esc(sec.topic)}</h2>
                <span class="topic-tier ${isT1 ? "is-t1" : ""}">${isT1 ? "TIER 1 · 核心主线" : "TIER 2 · 雷达追踪"}</span>
              </div>
              <span class="topic-count">${filtered.length} 篇</span>
            </div>
            ${noteHtml}
            ${cardsHtml}
          </section>`);
      });

      document.getElementById("spineList").innerHTML = spineParts.join("");
      document.getElementById("mobileTopics").innerHTML = mobileParts.join("");
      document.getElementById("content").innerHTML = secParts.join("");
      document.getElementById("statsFooter").textContent =
        `当前显示 ${visibleCount} / ${allPapers.length} 篇 · 已归档 ${ISSUES.length} 期`;

      setupScrollSpy();
    }

    ISSUES.forEach((iss, i) => {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = `${iss.date} · ${iss.sections.reduce((a, s) => a + s.papers.length, 0)} 篇`;
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
      document.querySelectorAll("#filterPills .filter-tab").forEach(b => b.classList.toggle("active", b === btn));
      render();
    });

    document.getElementById("sortGroup").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-sort]");
      if (!btn) return;
      activeSort = btn.dataset.sort;
      document.querySelectorAll("#sortGroup .sort-btn").forEach(b => b.classList.toggle("active", b === btn));
      render();
    });

    searchInput.addEventListener("input", () => {
      searchQuery = searchInput.value.trim().toLowerCase();
      render();
    });

    toggleExpandBtn.addEventListener("click", () => {
      allExpanded = !allExpanded;
      toggleExpandBtn.textContent = allExpanded ? "折叠为导读速扫" : "展开全部细读";
      document.querySelectorAll("details.drawer").forEach(d => { d.open = allExpanded; });
    });

    document.getElementById("content").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-star-id]");
      if (!btn) return;
      const pid = btn.dataset.starId;
      const title = btn.dataset.starTitle;
      const issueDate = ISSUES[currentIdx]?.date || "";
      if (starredMap[pid]) {
        delete starredMap[pid];
        btn.classList.remove("starred");
        btn.textContent = "☆";
        showToast("已取消收藏");
      } else {
        starredMap[pid] = { date: issueDate, paper_id: pid, title, verdict: "liked", note: "" };
        btn.classList.add("starred");
        btn.textContent = "★";
        showToast("已收藏 · 可从页脚导出反馈");
      }
      saveStars();
      if (activeFilter === "starred") render();
    });

    document.getElementById("exportStarBtn").addEventListener("click", async () => {
      const vals = Object.values(starredMap);
      if (!vals.length) {
        showToast("还没有点星收藏的论文");
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
      themeBtn.textContent = mode === "dark" ? "宣纸浅色" : "松烟深色";
      try { localStorage.setItem(STORAGE_KEY_THEME, mode); } catch {}
    }
    try {
      const savedTheme = localStorage.getItem(STORAGE_KEY_THEME);
      if (savedTheme === "dark") applyTheme("dark");
    } catch {}
    themeBtn.addEventListener("click", () => {
      const cur = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
      applyTheme(cur === "dark" ? "light" : "dark");
    });

    window.addEventListener("scroll", () => {
      const h = document.documentElement.scrollHeight - window.innerHeight;
      const pct = h > 0 ? Math.min(100, Math.max(0, (window.scrollY / h) * 100)) : 0;
      progressBar.style.width = pct.toFixed(1) + "%";
    }, { passive: true });

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
