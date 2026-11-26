#!/usr/bin/env python3
"""Validate a Daily Paper issue JSON against Schema v1.1, profile/topics.json, and agent-contract rules.

Zero external dependencies (Python 3.9+ stdlib only).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

VALID_SCHEMA_VERSIONS = {"1.0", "1.1"}
VALID_PRIORITIES = {"tier1", "tier2"}
VALID_LANES = {"fresh", "popular_backlist", "award", "supplement"}
VALID_READING_TIERS = {"deep", "scan"}
VALID_SIGNAL_KINDS = {"citations", "votes", "comments", "stars"}
VALID_DIRECTIONS = {
    "Code→Video",
    "Code→Image",
    "Image→Code",
    "Video→Code",
    "3D Code",
    "Other",
}
VALID_AWARD_SCOPES = {"main", "workshop", "honorable_mention"}

ALLOWED_ISSUE_KEYS = {"schema_version", "date", "timezone", "lead", "sections"}
ALLOWED_LEAD_KEYS = {"paper_id", "reason", "section_ref"}
ALLOWED_SECTION_KEYS = {"topic", "priority", "note", "papers"}
ALLOWED_PAPER_KEYS = {
    "id",
    "title",
    "authors_or_org",
    "published_on",
    "url",
    "repo_url",
    "lane",
    "reading_tier",
    "secondary_topics",
    "tags",
    "intro",
    "abstract_zh",
    "method",
    "results",
    "limitation",
    "heat",
    "directions",
    "revision_note",
    "award",
    "backlist_evidence",
}
REQUIRED_PAPER_KEYS = {
    "id",
    "title",
    "published_on",
    "url",
    "lane",
    "intro",
    "abstract_zh",
    "method",
    "results",
    "limitation",
    "heat",
}
ALLOWED_SIGNAL_KEYS = {"kind", "count", "source", "url", "observed_on", "approximate", "note"}
REQUIRED_SIGNAL_KEYS = {"kind", "count", "source", "url", "observed_on"}
ALLOWED_AWARD_KEYS = {"venue", "year", "name", "scope", "url"}
ALLOWED_BACKLIST_KEYS = {"summary", "url"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date(value: Any, ctx: str, errors: list[str]) -> dt.date | None:
    if not isinstance(value, str) or not DATE_RE.match(value):
        errors.append(f"{ctx}: must be YYYY-MM-DD string, got {value!r}")
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        errors.append(f"{ctx}: invalid calendar date {value!r}")
        return None


def check_nonempty_str(value: Any, ctx: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{ctx}: must be a non-empty string")
        return False
    return True


def check_https_url(value: Any, ctx: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not value.startswith("https://") or len(value) <= 8:
        errors.append(f"{ctx}: must be an https:// URL, got {value!r}")
        return False
    return True


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", title.lower())


def normalize_id(paper_id: str) -> str:
    pid = paper_id.strip().lower()
    if pid.startswith("arxiv:"):
        pid = re.sub(r"v\d+$", "", pid)
    return pid


def compute_heat_v1(heat: dict[str, Any]) -> tuple[int | None, int]:
    """Compute Heat v1 score and coverage (0..3) from raw verified signals."""
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
        comm_score = max(votes or 0, (comments or 0) * 2)
        total += comm_score
        coverage += 1
    if stars is not None:
        total += stars * 0.1
        coverage += 1

    if coverage == 0:
        return None, 0
    return int(round(total)), coverage


def load_archive_index(issues_dir: Path, exclude_file: Path) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    id_map: dict[str, str] = {}
    title_map: dict[str, str] = {}
    url_map: dict[str, str] = {}
    if not issues_dir.exists():
        return id_map, title_map, url_map
    exclude_resolved = exclude_file.resolve()
    for p in sorted(issues_dir.glob("*.json")):
        if p.resolve() == exclude_resolved:
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        issue_date = str(data.get("date") or p.stem)
        for sec in data.get("sections", []):
            for paper in sec.get("papers", []):
                if isinstance(paper.get("id"), str):
                    id_map.setdefault(normalize_id(paper["id"]), issue_date)
                if isinstance(paper.get("title"), str):
                    title_map.setdefault(normalize_title(paper["title"]), issue_date)
                if isinstance(paper.get("url"), str):
                    url_map.setdefault(paper["url"].strip(), issue_date)
    return id_map, title_map, url_map


def validate_issue(
    issue_path: Path,
    profile_path: Path,
    issues_dir: Path,
    skip_profile_check: bool = False,
) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    stats: dict[str, Any] = {
        "total_papers": 0,
        "by_tier": {"deep": 0, "scan": 0},
        "by_lane": {},
        "by_section": [],
    }

    try:
        data = json.loads(issue_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"Failed to parse JSON {issue_path}: {exc}"], warnings, stats

    if not isinstance(data, dict):
        return ["Root must be a JSON object"], warnings, stats

    extra_top = set(data.keys()) - ALLOWED_ISSUE_KEYS
    if extra_top:
        errors.append(f"Unexpected top-level keys: {sorted(extra_top)}")
    for req in ALLOWED_ISSUE_KEYS:
        if req not in data:
            errors.append(f"Missing required top-level key: {req}")

    if data.get("schema_version") not in VALID_SCHEMA_VERSIONS:
        errors.append(f"schema_version must be one of {sorted(VALID_SCHEMA_VERSIONS)}, got {data.get('schema_version')!r}")

    issue_date = parse_date(data.get("date"), "date", errors)
    if data.get("timezone") != "Asia/Shanghai":
        errors.append(f"timezone must be 'Asia/Shanghai', got {data.get('timezone')!r}")

    # Load profile topics if available
    expected_topics: list[str] = []
    require_dir_topics: set[str] = {"多模态编程"}
    if not skip_profile_check and profile_path.exists():
        try:
            prof = json.loads(profile_path.read_text(encoding="utf-8"))
            for t in prof.get("topics", []):
                name = t.get("name")
                if isinstance(name, str):
                    expected_topics.append(name)
                    if t.get("require_directions"):
                        require_dir_topics.add(name)
        except Exception as exc:
            warnings.append(f"Could not read profile {profile_path}: {exc}")

    # Archive dedup index
    arch_ids, arch_titles, arch_urls = load_archive_index(issues_dir, issue_path)

    # Validate lead
    lead = data.get("lead")
    lead_paper_id: str | None = None
    if not isinstance(lead, dict):
        errors.append("lead must be an object")
    else:
        extra_lead = set(lead.keys()) - ALLOWED_LEAD_KEYS
        if extra_lead:
            errors.append(f"lead has unexpected keys: {sorted(extra_lead)}")
        if check_nonempty_str(lead.get("paper_id"), "lead.paper_id", errors):
            lead_paper_id = lead["paper_id"]
        check_nonempty_str(lead.get("reason"), "lead.reason", errors)
        if "section_ref" in lead:
            check_nonempty_str(lead.get("section_ref"), "lead.section_ref", errors)

    # Validate sections
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("sections must be a non-empty array")
        return errors, warnings, stats

    actual_topics: list[str] = []
    seen_ids: set[str] = set()
    all_raw_ids: set[str] = set()

    for s_idx, sec in enumerate(sections):
        s_ctx = f"sections[{s_idx}]"
        if not isinstance(sec, dict):
            errors.append(f"{s_ctx}: must be an object")
            continue
        extra_s = set(sec.keys()) - ALLOWED_SECTION_KEYS
        if extra_s:
            errors.append(f"{s_ctx}: unexpected keys {sorted(extra_s)}")
        topic = sec.get("topic")
        if check_nonempty_str(topic, f"{s_ctx}.topic", errors):
            actual_topics.append(topic)
            s_ctx = f"sections[{s_idx}:{topic}]"
        if "priority" in sec and sec["priority"] not in VALID_PRIORITIES:
            errors.append(f"{s_ctx}.priority: invalid value {sec['priority']!r}")
        if "note" in sec:
            check_nonempty_str(sec.get("note"), f"{s_ctx}.note", errors)

        papers = sec.get("papers")
        if not isinstance(papers, list):
            errors.append(f"{s_ctx}.papers: must be an array")
            continue
        if len(papers) > 12:
            errors.append(f"{s_ctx}.papers: max 12 items allowed, got {len(papers)}")
        if len(papers) == 0 and "note" not in sec:
            errors.append(f"{s_ctx}: empty papers array requires a non-empty 'note'")

        stats["by_section"].append({"topic": topic, "count": len(papers)})

        for p_idx, paper in enumerate(papers):
            p_ctx = f"{s_ctx}.papers[{p_idx}]"
            if not isinstance(paper, dict):
                errors.append(f"{p_ctx}: must be an object")
                continue
            extra_p = set(paper.keys()) - ALLOWED_PAPER_KEYS
            if extra_p:
                errors.append(f"{p_ctx}: unexpected keys {sorted(extra_p)}")
            for req in REQUIRED_PAPER_KEYS:
                if req not in paper:
                    errors.append(f"{p_ctx}: missing required key '{req}'")

            pid = paper.get("id")
            if check_nonempty_str(pid, f"{p_ctx}.id", errors):
                all_raw_ids.add(pid)
                norm_pid = normalize_id(pid)
                if norm_pid in seen_ids:
                    errors.append(f"{p_ctx}.id: duplicate paper id within issue ({pid!r})")
                seen_ids.add(norm_pid)
                p_ctx = f"{s_ctx}.papers[{p_idx}:{pid}]"

            title = paper.get("title")
            check_nonempty_str(title, f"{p_ctx}.title", errors)
            if "authors_or_org" in paper:
                check_nonempty_str(paper.get("authors_or_org"), f"{p_ctx}.authors_or_org", errors)
            pub_date = parse_date(paper.get("published_on"), f"{p_ctx}.published_on", errors)
            url = paper.get("url")
            check_https_url(url, f"{p_ctx}.url", errors)
            if "repo_url" in paper:
                check_https_url(paper.get("repo_url"), f"{p_ctx}.repo_url", errors)

            lane = paper.get("lane")
            if lane not in VALID_LANES:
                errors.append(f"{p_ctx}.lane: must be one of {sorted(VALID_LANES)}, got {lane!r}")
            else:
                stats["by_lane"][lane] = stats["by_lane"].get(lane, 0) + 1

            reading_tier = paper.get("reading_tier", "deep")
            if "reading_tier" in paper and reading_tier not in VALID_READING_TIERS:
                errors.append(f"{p_ctx}.reading_tier: invalid value {reading_tier!r}")
            elif reading_tier in stats["by_tier"]:
                stats["by_tier"][reading_tier] += 1

            for list_field in ("secondary_topics", "tags"):
                if list_field in paper:
                    val = paper[list_field]
                    if not isinstance(val, list) or any(not isinstance(x, str) or not x.strip() for x in val):
                        errors.append(f"{p_ctx}.{list_field}: must be an array of non-empty strings")
                    elif len(set(val)) != len(val):
                        errors.append(f"{p_ctx}.{list_field}: must contain unique items")

            for text_field in ("intro", "abstract_zh", "method", "results", "limitation"):
                check_nonempty_str(paper.get(text_field), f"{p_ctx}.{text_field}", errors)

            if "revision_note" in paper:
                check_nonempty_str(paper.get("revision_note"), f"{p_ctx}.revision_note", errors)

            # Lane vs published_on checks
            if issue_date and pub_date:
                age_days = (issue_date - pub_date).days
                if age_days < -1:
                    warnings.append(f"{p_ctx}: published_on ({pub_date}) is after issue date ({issue_date})")
                if lane == "popular_backlist" and age_days <= 14:
                    errors.append(
                        f"{p_ctx}: lane='popular_backlist' requires paper age > 14 days (got {age_days} days)"
                    )
                if lane == "fresh" and age_days > 14 and "revision_note" not in paper:
                    errors.append(
                        f"{p_ctx}: lane='fresh' paper is {age_days} days old (>14) without 'revision_note'"
                    )

            # Multimodal directions requirement
            if topic in require_dir_topics and "directions" not in paper:
                errors.append(f"{p_ctx}: topic '{topic}' requires 'directions'")
            if "directions" in paper:
                dirs = paper["directions"]
                if not isinstance(dirs, list) or not dirs:
                    errors.append(f"{p_ctx}.directions: must be a non-empty array")
                else:
                    bad = [d for d in dirs if d not in VALID_DIRECTIONS]
                    if bad:
                        errors.append(f"{p_ctx}.directions: invalid values {bad}")
                    if len(set(dirs)) != len(dirs):
                        errors.append(f"{p_ctx}.directions: must contain unique items")

            # Conditional requirements for award / popular_backlist
            if lane == "award" and "award" not in paper:
                errors.append(f"{p_ctx}: lane='award' requires 'award' object")
            if "award" in paper:
                aw = paper["award"]
                if not isinstance(aw, dict):
                    errors.append(f"{p_ctx}.award: must be an object")
                else:
                    extra_aw = set(aw.keys()) - ALLOWED_AWARD_KEYS
                    if extra_aw:
                        errors.append(f"{p_ctx}.award: unexpected keys {sorted(extra_aw)}")
                    for req in ALLOWED_AWARD_KEYS:
                        if req not in aw:
                            errors.append(f"{p_ctx}.award: missing '{req}'")
                    check_nonempty_str(aw.get("venue"), f"{p_ctx}.award.venue", errors)
                    check_nonempty_str(aw.get("name"), f"{p_ctx}.award.name", errors)
                    if not isinstance(aw.get("year"), int) or isinstance(aw.get("year"), bool) or aw["year"] < 1900:
                        errors.append(f"{p_ctx}.award.year: must be integer >= 1900")
                    if aw.get("scope") not in VALID_AWARD_SCOPES:
                        errors.append(f"{p_ctx}.award.scope: must be one of {sorted(VALID_AWARD_SCOPES)}")
                    check_https_url(aw.get("url"), f"{p_ctx}.award.url", errors)

            if lane == "popular_backlist" and "backlist_evidence" not in paper:
                errors.append(f"{p_ctx}: lane='popular_backlist' requires 'backlist_evidence'")
            if "backlist_evidence" in paper:
                be = paper["backlist_evidence"]
                if not isinstance(be, list) or not be:
                    errors.append(f"{p_ctx}.backlist_evidence: must be a non-empty array")
                else:
                    for b_idx, item in enumerate(be):
                        if not isinstance(item, dict):
                            errors.append(f"{p_ctx}.backlist_evidence[{b_idx}]: must be an object")
                            continue
                        extra_b = set(item.keys()) - ALLOWED_BACKLIST_KEYS
                        if extra_b:
                            errors.append(f"{p_ctx}.backlist_evidence[{b_idx}]: unexpected keys {sorted(extra_b)}")
                        check_nonempty_str(item.get("summary"), f"{p_ctx}.backlist_evidence[{b_idx}].summary", errors)
                        check_https_url(item.get("url"), f"{p_ctx}.backlist_evidence[{b_idx}].url", errors)

            # Heat validation
            heat = paper.get("heat")
            if not isinstance(heat, dict):
                errors.append(f"{p_ctx}.heat: must be an object")
            else:
                has_signals = "signals" in heat
                has_unavail = "unavailable" in heat
                extra_h = set(heat.keys()) - {"signals", "unavailable"}
                if extra_h:
                    errors.append(f"{p_ctx}.heat: unexpected keys {sorted(extra_h)}")
                if has_signals == has_unavail:
                    errors.append(f"{p_ctx}.heat: must specify exactly one of 'signals' or 'unavailable'")
                elif has_unavail:
                    check_nonempty_str(heat.get("unavailable"), f"{p_ctx}.heat.unavailable", errors)
                else:
                    sigs = heat.get("signals")
                    if not isinstance(sigs, list) or not sigs:
                        errors.append(f"{p_ctx}.heat.signals: must be a non-empty array")
                    else:
                        seen_kinds: list[str] = []
                        for sig_idx, sig in enumerate(sigs):
                            sig_ctx = f"{p_ctx}.heat.signals[{sig_idx}]"
                            if not isinstance(sig, dict):
                                errors.append(f"{sig_ctx}: must be an object")
                                continue
                            extra_sig = set(sig.keys()) - ALLOWED_SIGNAL_KEYS
                            if extra_sig:
                                errors.append(f"{sig_ctx}: unexpected keys {sorted(extra_sig)}")
                            for req in REQUIRED_SIGNAL_KEYS:
                                if req not in sig:
                                    errors.append(f"{sig_ctx}: missing '{req}'")
                            kind = sig.get("kind")
                            if kind not in VALID_SIGNAL_KINDS:
                                errors.append(f"{sig_ctx}.kind: invalid value {kind!r}")
                            else:
                                seen_kinds.append(kind)
                            cnt = sig.get("count")
                            if not isinstance(cnt, int) or isinstance(cnt, bool) or cnt < 0:
                                errors.append(f"{sig_ctx}.count: must be non-negative integer")
                            check_nonempty_str(sig.get("source"), f"{sig_ctx}.source", errors)
                            check_https_url(sig.get("url"), f"{sig_ctx}.url", errors)
                            parse_date(sig.get("observed_on"), f"{sig_ctx}.observed_on", errors)
                            if "approximate" in sig and not isinstance(sig["approximate"], bool):
                                errors.append(f"{sig_ctx}.approximate: must be boolean")
                            if "note" in sig:
                                check_nonempty_str(sig.get("note"), f"{sig_ctx}.note", errors)
                        if len(set(seen_kinds)) != len(seen_kinds):
                            warnings.append(f"{p_ctx}.heat.signals: duplicate signal kinds found ({seen_kinds}); policy prefers single verified source per dimension")

            # Cross-issue deduplication
            if isinstance(pid, str) and "revision_note" not in paper:
                norm_pid = normalize_id(pid)
                if norm_pid in arch_ids:
                    errors.append(
                        f"{p_ctx}: paper id {pid!r} already archived on {arch_ids[norm_pid]} (add 'revision_note' if major revision)"
                    )
                elif isinstance(title, str) and normalize_title(title) in arch_titles:
                    errors.append(
                        f"{p_ctx}: paper title {title!r} already archived on {arch_titles[normalize_title(title)]}"
                    )
                elif isinstance(url, str) and url.strip() in arch_urls:
                    errors.append(
                        f"{p_ctx}: paper url {url!r} already archived on {arch_urls[url.strip()]}"
                    )

            stats["total_papers"] += 1

    # Check topic ordering against profile
    if expected_topics and actual_topics != expected_topics:
        errors.append(
            f"sections topic order/names mismatch profile/topics.json:\n"
            f"  expected: {expected_topics}\n"
            f"  actual:   {actual_topics}"
        )

    # Check lead exists
    if lead_paper_id and lead_paper_id not in all_raw_ids:
        errors.append(f"lead.paper_id {lead_paper_id!r} not found in any section's papers")

    if stats["total_papers"] == 0:
        errors.append("Issue contains 0 total papers; refusing to validate an empty issue")

    return errors, warnings, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Daily Paper issue JSON file.")
    parser.add_argument("issue", type=Path, help="Path to issue JSON file")
    parser.add_argument(
        "--profile",
        type=Path,
        default=REPO_ROOT / "profile" / "topics.json",
        help="Path to profile/topics.json",
    )
    parser.add_argument(
        "--issues-dir",
        type=Path,
        default=REPO_ROOT / "issues",
        help="Directory of archived issues for cross-issue dedup",
    )
    parser.add_argument(
        "--skip-profile-check",
        action="store_true",
        help="Do not require sections to match profile/topics.json order",
    )
    args = parser.parse_args()

    errors, warnings, stats = validate_issue(
        issue_path=args.issue,
        profile_path=args.profile,
        issues_dir=args.issues_dir,
        skip_profile_check=args.skip_profile_check,
    )

    for w in warnings:
        print(f"[WARN]  {w}")
    for e in errors:
        print(f"[ERROR] {e}")

    if errors:
        print(f"\nFAILED: {len(errors)} error(s), {len(warnings)} warning(s).")
        return 1

    sec_summary = ", ".join(f"{s['topic']}={s['count']}" for s in stats["by_section"])
    print(
        f"OK: {args.issue} passed validation | "
        f"total={stats['total_papers']} (deep={stats['by_tier']['deep']}, scan={stats['by_tier']['scan']}) | "
        f"lanes={stats['by_lane']} | sections=[{sec_summary}]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
