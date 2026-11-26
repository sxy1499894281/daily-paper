#!/usr/bin/env python3
"""Fetch fresh paper candidates from arXiv + Hugging Face Daily Papers and enrich with OpenAlex/GitHub signals.

Zero external dependencies (Python 3.9+ stdlib only).
Designed for high-recall fresh tracking driven by profile/topics.json & profile/watchlist.json.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ARXIV_API = "https://export.arxiv.org/api/query"
HF_DAILY_API = "https://huggingface.co/api/daily_papers"
OPENALEX_API = "https://api.openalex.org/works/https://doi.org/10.48550/arXiv.{arxiv_id}"
GITHUB_REPO_API = "https://api.github.com/repos/{owner}/{repo}"

USER_AGENT = "daily-paper-skill/1.1 (https://github.com/sxy1499894281/daily-paper)"
ARXIV_ID_RE = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
GITHUB_URL_RE = re.compile(r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def shanghai_today() -> dt.date:
    tz = dt.timezone(dt.timedelta(hours=8))
    return dt.datetime.now(tz).date()


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", title.lower())


def normalize_arxiv_id(raw: str) -> str | None:
    m = ARXIV_ID_RE.search(raw)
    return m.group(1) if m else None


def http_get_bytes(url: str, timeout: int = 20, headers: dict[str, str] | None = None) -> bytes | None:
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[warn] GET failed {url}: {exc}", file=sys.stderr)
        return None


def http_get_json(url: str, timeout: int = 20, headers: dict[str, str] | None = None) -> Any | None:
    raw = http_get_bytes(url, timeout=timeout, headers=headers)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        print(f"[warn] JSON parse failed {url}: {exc}", file=sys.stderr)
        return None


def extract_github_repos(text: str) -> list[str]:
    repos: list[str] = []
    seen: set[str] = set()
    for owner, repo in GITHUB_URL_RE.findall(text or ""):
        repo_clean = repo.rstrip(".,;:)]}'\"")
        if repo_clean.endswith(".git"):
            repo_clean = repo_clean[:-4]
        if owner.lower() in {"sponsors", "features", "topics", "orgs"}:
            continue
        url = f"https://github.com/{owner}/{repo_clean}"
        key = url.lower()
        if key not in seen:
            seen.add(key)
            repos.append(url)
    return repos


def load_archive_index(issues_dir: Path) -> tuple[set[str], set[str], set[str]]:
    ids: set[str] = set()
    titles: set[str] = set()
    urls: set[str] = set()
    if not issues_dir.exists():
        return ids, titles, urls
    for p in sorted(issues_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for sec in data.get("sections", []):
            for paper in sec.get("papers", []):
                pid = str(paper.get("id") or "").strip().lower()
                if pid:
                    ids.add(re.sub(r"v\d+$", "", pid))
                title = str(paper.get("title") or "")
                if title:
                    titles.add(normalize_title(title))
                url = str(paper.get("url") or "").strip()
                if url:
                    urls.add(url)
    return ids, titles, urls


def query_arxiv(search_query: str, max_results: int = 12) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "search_query": search_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    raw = http_get_bytes(f"{ARXIV_API}?{params}", timeout=25)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        print(f"[warn] arXiv XML parse error: {exc}", file=sys.stderr)
        return []

    results: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        entry_id = (entry.findtext("atom:id", default="", namespaces=ATOM_NS) or "").strip()
        arxiv_id = normalize_arxiv_id(entry_id)
        if not arxiv_id:
            continue
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").split())
        abstract = " ".join((entry.findtext("atom:summary", default="", namespaces=ATOM_NS) or "").split())
        published = (entry.findtext("atom:published", default="", namespaces=ATOM_NS) or "")[:10]
        updated = (entry.findtext("atom:updated", default="", namespaces=ATOM_NS) or "")[:10]
        authors = [
            (a.findtext("atom:name", default="", namespaces=ATOM_NS) or "").strip()
            for a in entry.findall("atom:author", ATOM_NS)
        ]
        categories = [c.attrib.get("term", "") for c in entry.findall("atom:category", ATOM_NS)]
        comment = (entry.findtext("arxiv:comment", default="", namespaces=ATOM_NS) or "").strip()
        repo_urls = extract_github_repos(f"{abstract} {comment}")
        results.append(
            {
                "id": f"arxiv:{arxiv_id}",
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": authors[:8],
                "published_on": published,
                "updated_on": updated,
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "abstract": abstract,
                "categories": [c for c in categories if c],
                "comment": comment,
                "repo_urls": repo_urls,
                "sources": ["arxiv"],
            }
        )
    return results


def fetch_hf_daily_papers(target_date: dt.date, lookback_days: int = 3) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for offset in range(max(1, lookback_days)):
        d = target_date - dt.timedelta(days=offset)
        payload = http_get_json(f"{HF_DAILY_API}?date={d.isoformat()}", timeout=20)
        if not isinstance(payload, list):
            continue
        for item in payload:
            paper = item.get("paper") or {}
            raw_id = str(paper.get("id") or "")
            arxiv_id = normalize_arxiv_id(raw_id)
            if not arxiv_id:
                continue
            key = f"arxiv:{arxiv_id}"
            title = " ".join(str(paper.get("title") or item.get("title") or "").split())
            abstract = " ".join(str(paper.get("summary") or item.get("summary") or "").split())
            pub = str(paper.get("publishedAt") or item.get("publishedAt") or d.isoformat())[:10]
            upvotes = paper.get("upvotes")
            num_comments = item.get("numComments")
            gh_repo = paper.get("githubRepo")
            repo_urls = extract_github_repos(abstract)
            if isinstance(gh_repo, str) and gh_repo.startswith("https://github.com/"):
                if gh_repo.lower() not in {r.lower() for r in repo_urls}:
                    repo_urls.insert(0, gh_repo)
            authors = [
                str(a.get("name") or "").strip()
                for a in (paper.get("authors") or [])
                if isinstance(a, dict) and a.get("name")
            ]
            seen[key] = {
                "id": key,
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": authors[:8],
                "published_on": pub,
                "updated_on": pub,
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "abstract": abstract,
                "categories": [],
                "comment": "",
                "repo_urls": repo_urls,
                "hf": {
                    "url": f"https://huggingface.co/papers/{arxiv_id}",
                    "votes": upvotes if isinstance(upvotes, int) else None,
                    "comments": num_comments if isinstance(num_comments, int) else None,
                    "observed_on": target_date.isoformat(),
                },
                "sources": ["huggingface_daily_papers"],
            }
    return list(seen.values())


def enrich_openalex(arxiv_id: str, observed_on: str) -> dict[str, Any] | None:
    email = os.environ.get("OPENALEX_EMAIL", "")
    url = OPENALEX_API.format(arxiv_id=arxiv_id)
    if email:
        url = f"{url}?mailto={urllib.parse.quote(email)}"
    data = http_get_json(url, timeout=15)
    if not isinstance(data, dict) or "cited_by_count" not in data:
        return None
    oa_id = data.get("id") or url
    return {
        "kind": "citations",
        "count": int(data["cited_by_count"]),
        "source": "OpenAlex",
        "url": str(oa_id),
        "observed_on": observed_on,
    }


_GH_TOKEN_CACHE: str | None = None


def resolve_github_token() -> str | None:
    global _GH_TOKEN_CACHE
    if _GH_TOKEN_CACHE is not None:
        return _GH_TOKEN_CACHE or None
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        try:
            proc = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                token = proc.stdout.strip()
        except Exception:
            token = ""
    _GH_TOKEN_CACHE = token or ""
    return _GH_TOKEN_CACHE or None


def enrich_github(repo_url: str, observed_on: str) -> dict[str, Any] | None:
    m = GITHUB_URL_RE.match(repo_url)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = resolve_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = http_get_json(GITHUB_REPO_API.format(owner=owner, repo=repo), timeout=15, headers=headers)
    if not isinstance(data, dict) or "stargazers_count" not in data:
        return None
    return {
        "kind": "stars",
        "count": int(data["stargazers_count"]),
        "source": "GitHub",
        "url": str(data.get("html_url") or repo_url),
        "observed_on": observed_on,
    }


def match_topics_for_text(text: str, topics: list[dict[str, Any]], watchlist: dict[str, Any]) -> tuple[list[str], list[str]]:
    lowered = text.lower()
    matched_topics: list[str] = []
    matched_benchmarks: list[str] = []
    for bm in watchlist.get("priority_benchmarks", []):
        if bm.lower() in lowered:
            matched_benchmarks.append(bm)

    keyword_hints: dict[str, list[str]] = {
        "computer-use": ["computer use", "computer-use", "desktop agent", "os agent", "osworld", "appworld", "cross-app"],
        "multimodal-coding": ["image to code", "video to code", "code to video", "code to image", "3d code", "manim", "svg", "blender", "cad", "tikz", "screenshot to code", "ui to code", "chart to code"],
        "gui-agent": ["gui agent", "gui grounding", "mobile agent", "web agent", "ui grounding", "screen grounding", "androidworld", "browsergym", "webarena", "visualwebarena"],
        "env-scaling": ["environment synthesis", "synthetic environment", "mock app", "verifier generation", "verifiable environment", "gym", "sandbox", "rollout", "resettable", "task generation"],
        "rsi": ["self-improving", "self-improvement", "recursive self-improvement", "self-evolving", "skill evolution", "automated agent design", "darwin godel", "self-play"],
        "game-agent": ["game agent", "playtesting", "game benchmark", "minecraft", "starcraft", "nethack", "pokemon", "video game", "balrog"],
        "world-model": ["world model", "action world model", "state transition", "environment simulator", "next-state", "gui world", "digital world", "trajectory to world"],
        "personal-agent": ["personal agent", "personal assistant", "proactive assistant", "long-term memory", "user preference", "lifelong personalization", "mypcbench", "apprenticebench"],
    }
    for t in topics:
        tid = t.get("id", "")
        tname = t.get("name", "")
        hints = keyword_hints.get(tid, []) + [a.lower() for a in t.get("anchors", [])]
        if any(h in lowered for h in hints):
            matched_topics.append(tname)
    return matched_topics, matched_benchmarks


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch fresh paper candidates driven by profile/topics.json.")
    parser.add_argument("--date", help="Target Beijing date YYYY-MM-DD (default: today Asia/Shanghai)")
    parser.add_argument("--days", type=int, default=14, help="Lookback window in days for fresh papers (default: 14)")
    parser.add_argument("--max-per-query", type=int, default=8, help="Max arXiv results per query (default: 8)")
    parser.add_argument("--hf-days", type=int, default=3, help="Days of HF Daily Papers to fetch (default: 3)")
    parser.add_argument("--skip-hf", action="store_true", help="Skip Hugging Face Daily Papers API")
    parser.add_argument("--skip-arxiv", action="store_true", help="Skip arXiv API")
    parser.add_argument("--enrich-limit", type=int, default=20, help="Max candidates to enrich via OpenAlex/GitHub (0 disables)")
    parser.add_argument("--profile", type=Path, default=REPO_ROOT / "profile" / "topics.json")
    parser.add_argument("--watchlist", type=Path, default=REPO_ROOT / "profile" / "watchlist.json")
    parser.add_argument("--issues-dir", type=Path, default=REPO_ROOT / "issues")
    parser.add_argument("--output", type=Path, required=True, help="Output candidates JSON path")
    args = parser.parse_args()

    target_date = dt.date.fromisoformat(args.date) if args.date else shanghai_today()
    cutoff_date = target_date - dt.timedelta(days=args.days)

    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    watchlist = json.loads(args.watchlist.read_text(encoding="utf-8")) if args.watchlist.exists() else {}
    topics: list[dict[str, Any]] = profile.get("topics", [])
    arch_ids, arch_titles, arch_urls = load_archive_index(args.issues_dir)

    candidates: dict[str, dict[str, Any]] = {}

    def merge_candidate(item: dict[str, Any], topic_name: str | None = None) -> None:
        cid = item["id"]
        if cid not in candidates:
            item["matched_topics"] = []
            candidates[cid] = item
        else:
            existing = candidates[cid]
            for src in item.get("sources", []):
                if src not in existing["sources"]:
                    existing["sources"].append(src)
            for repo in item.get("repo_urls", []):
                if repo.lower() not in {r.lower() for r in existing["repo_urls"]}:
                    existing["repo_urls"].append(repo)
            if "hf" in item and "hf" not in existing:
                existing["hf"] = item["hf"]
            if len(item.get("abstract", "")) > len(existing.get("abstract", "")):
                existing["abstract"] = item["abstract"]
        if topic_name and topic_name not in candidates[cid]["matched_topics"]:
            candidates[cid]["matched_topics"].append(topic_name)

    if not args.skip_arxiv:
        for t in topics:
            tname = t["name"]
            for q in t.get("arxiv_queries", []):
                print(f"[arxiv] {tname}: {q}", file=sys.stderr)
                rows = query_arxiv(q, max_results=args.max_per_query)
                for r in rows:
                    try:
                        pdate = dt.date.fromisoformat(r["published_on"])
                    except ValueError:
                        continue
                    if pdate < cutoff_date:
                        continue
                    merge_candidate(r, topic_name=tname)
                time.sleep(0.4)

    if not args.skip_hf:
        print(f"[hf] fetching {args.hf_days} day(s) ending {target_date.isoformat()}", file=sys.stderr)
        for r in fetch_hf_daily_papers(target_date, lookback_days=args.hf_days):
            matched, _ = match_topics_for_text(f"{r['title']} {r['abstract']}", topics, watchlist)
            if matched:
                for m_topic in matched:
                    merge_candidate(r, topic_name=m_topic)

    # Secondary topic tagging, benchmark detection, and archive dedup flags
    tier_rank = {t["name"]: (0 if t.get("priority") == "tier1" else 1) for t in topics}
    for c in candidates.values():
        inferred_topics, matched_bms = match_topics_for_text(f"{c['title']} {c['abstract']}", topics, watchlist)
        for mt in inferred_topics:
            if mt not in c["matched_topics"]:
                c["matched_topics"].append(mt)
        c["matched_benchmarks"] = matched_bms
        c["already_archived"] = (
            c["id"].lower() in arch_ids
            or normalize_title(c["title"]) in arch_titles
            or c["url"] in arch_urls
        )
        c["top_tier"] = min((tier_rank.get(t, 2) for t in c["matched_topics"]), default=2)

    # Sort non-archived first, then Tier 1, recent 7 days, and benchmark/repo/HF signal density
    ordered = sorted(
        candidates.values(),
        key=lambda c: (
            1 if c["already_archived"] else 0,
            c["top_tier"],
            c.get("published_on", "") < (target_date - dt.timedelta(days=7)).isoformat(),
            -(len(c["matched_benchmarks"]) + (1 if c.get("repo_urls") else 0) + (1 if c.get("hf") else 0)),
        ),
    )

    if args.enrich_limit > 0:
        enriched = 0
        for c in ordered:
            if c["already_archived"]:
                continue
            if enriched >= args.enrich_limit:
                break
            signals: list[dict[str, Any]] = []
            hf = c.get("hf")
            if isinstance(hf, dict):
                if isinstance(hf.get("votes"), int):
                    signals.append(
                        {
                            "kind": "votes",
                            "count": hf["votes"],
                            "source": "Hugging Face Papers",
                            "url": hf["url"],
                            "observed_on": hf["observed_on"],
                        }
                    )
                if isinstance(hf.get("comments"), int) and hf["comments"] > 0:
                    signals.append(
                        {
                            "kind": "comments",
                            "count": hf["comments"],
                            "source": "Hugging Face Papers",
                            "url": hf["url"],
                            "observed_on": hf["observed_on"],
                        }
                    )
            if c.get("arxiv_id"):
                oa = enrich_openalex(c["arxiv_id"], target_date.isoformat())
                if oa:
                    signals.append(oa)
            if c.get("repo_urls"):
                gh = enrich_github(c["repo_urls"][0], target_date.isoformat())
                if gh:
                    signals.append(gh)
            c["prefetched_heat_signals"] = signals
            enriched += 1
            time.sleep(0.15)

    summary_by_topic: dict[str, int] = {t["name"]: 0 for t in topics}
    for c in ordered:
        if not c["already_archived"]:
            for mt in c["matched_topics"]:
                if mt in summary_by_topic:
                    summary_by_topic[mt] += 1

    output_payload = {
        "generated_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds"),
        "target_date": target_date.isoformat(),
        "window_days": args.days,
        "cutoff_date": cutoff_date.isoformat(),
        "total_candidates": len(ordered),
        "new_candidates": sum(1 for c in ordered if not c["already_archived"]),
        "summary_by_topic": summary_by_topic,
        "candidates": ordered,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Saved {output_payload['total_candidates']} candidates "
        f"({output_payload['new_candidates']} new) to {args.output}"
    )
    print("By topic (new):", json.dumps(summary_by_topic, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
