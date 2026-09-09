"""Shared schema and parsers for user-authored research records."""
import json
import re


ENTRY_TYPES = {"thesis", "information", "question", "observation"}
RELATIONS = {"support", "oppose", "timing", "alternative", "related"}


def _split_symbols(value):
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[,，\s]+", str(value or ""))
    return list(dict.fromkeys(str(x).upper().replace("$", "").strip()
                              for x in raw if str(x).strip()))


def _number(value):
    try:
        return min(100.0, max(0.0, float(str(value).replace("%", "").strip())))
    except (TypeError, ValueError):
        return None


def normalize_entry(raw, issue_number=None, issue_url=""):
    kind = str(raw.get("type", raw.get("记录类型", "observation"))).lower().strip()
    if kind not in ENTRY_TYPES:
        kind = "observation"
    visibility = str(raw.get("visibility", raw.get("公开状态", "private"))).lower().strip()
    public = visibility in {"public", "公开", "yes", "true"} or raw.get("public") is True
    entry_id = str(raw.get("id") or (f"R-{issue_number}" if issue_number else "")).strip()
    return {
        "id": entry_id,
        "type": kind,
        "title": str(raw.get("title", raw.get("标题", ""))).strip(),
        "statement": str(raw.get("statement", raw.get("核心内容", ""))).strip(),
        "symbols": _split_symbols(raw.get("symbols", raw.get("相关代码", []))),
        "horizon": str(raw.get("horizon", raw.get("时间范围", ""))).strip(),
        "probability": _number(raw.get("probability", raw.get("当前概率"))),
        "supporting_conditions": str(raw.get("supporting_conditions", raw.get("支持条件", ""))).strip(),
        "falsifiers": str(raw.get("falsifiers", raw.get("证伪条件", ""))).strip(),
        "alternative_explanations": str(raw.get("alternative_explanations", raw.get("替代解释", ""))).strip(),
        "source_url": str(raw.get("source_url", raw.get("来源链接", ""))).strip(),
        "visibility": "public" if public else "private",
        "input_channel": str(raw.get("input_channel", raw.get("输入渠道", "dashboard"))).strip(),
        "status": str(raw.get("status", "active")).strip(),
        "issue_number": issue_number,
        "issue_url": issue_url,
    }


def parse_issue_body(body, issue_number=None, issue_url=""):
    """Parse dashboard JSON blocks and native GitHub Issue Form submissions."""
    body = str(body or "")
    match = re.search(r"```research-entry\s*(\{.*?\})\s*```", body, re.S)
    if match:
        try:
            return normalize_entry(json.loads(match.group(1)), issue_number, issue_url)
        except json.JSONDecodeError:
            return None

    fields = {}
    chunks = re.split(r"^###\s+", body, flags=re.M)
    aliases = {
        "记录类型": "type", "标题": "title", "核心内容": "statement",
        "相关代码": "symbols", "时间范围": "horizon", "当前概率": "probability",
        "支持条件": "supporting_conditions", "证伪条件": "falsifiers",
        "替代解释": "alternative_explanations", "来源链接": "source_url",
        "公开状态": "visibility", "输入渠道": "input_channel",
    }
    for chunk in chunks[1:]:
        heading, _, value = chunk.partition("\n")
        key = aliases.get(heading.strip())
        if key:
            fields[key] = value.strip().replace("_No response_", "")
    if not fields.get("title") or not fields.get("statement"):
        return None
    return normalize_entry(fields, issue_number, issue_url)


def public_entries(issues):
    entries = []
    for issue in issues:
        entry = parse_issue_body(issue.get("body"), issue.get("number"), issue.get("html_url", ""))
        if entry and entry["visibility"] == "public":
            entry["created_at"] = issue.get("created_at")
            entry["updated_at"] = issue.get("updated_at")
            entries.append(entry)
    return sorted(entries, key=lambda x: x.get("updated_at") or "", reverse=True)
