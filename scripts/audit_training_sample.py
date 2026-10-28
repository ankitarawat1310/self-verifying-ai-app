"""Audit local JSONL conversations without executing their contents.

This reports structural quality, not correctness, licensing or benchmark leakage.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def audit(path):
    rows = []
    seen = {}
    roles = Counter()
    with path.open(encoding="utf-8-sig") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            issues = []
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                rows.append({"line": line_number, "issues": ["invalid_json"]})
                continue
            if not isinstance(record, dict):
                rows.append({"line": line_number, "issues": ["record_not_object"]})
                continue
            messages = record.get("conversations")
            characters = 0
            row_roles = Counter()
            if not isinstance(messages, list) or not messages:
                issues.append("missing_conversations")
                messages = []
            for message in messages:
                if not isinstance(message, dict):
                    issues.append("invalid_message")
                    continue
                role = message.get("role")
                if role not in ("system", "user", "assistant", "tool", "function"):
                    issues.append("unknown_role")
                else:
                    row_roles[role] += 1
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    issues.append("empty_or_nontext_content")
                else:
                    characters += len(content)
            roles.update(row_roles)
            if not row_roles["user"]:
                issues.append("no_user_message")
            if not row_roles["assistant"]:
                issues.append("no_assistant_message")
            digest = hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            duplicate_of = seen.get(digest)
            if duplicate_of is not None:
                issues.append("duplicate_conversation")
            seen.setdefault(digest, line_number)
            rows.append({
                "line": line_number, "task": record.get("task"),
                "run_id": record.get("run_id"), "messages": len(messages),
                "characters": characters, "conversation_sha256": digest,
                "duplicate_of_line": duplicate_of,
                "result_present": record.get("result") is not None,
                "issues": sorted(set(issues)),
            })
    return {
        "input": str(path), "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "records": len(rows),
        "records_without_structural_issues": sum(not r["issues"] for r in rows),
        "records_with_result": sum(r.get("result_present", False) for r in rows),
        "issue_counts": dict(Counter(i for r in rows for i in r["issues"])),
        "message_roles": dict(roles), "rows": rows,
        "limitations": [
            "A present result field is not proof of success; its schema must be verified.",
            "Model statements of success are not independent verifier evidence.",
            "Token lengths require each selected model's tokenizer and chat template.",
            "Licence, source revision, near duplicates and benchmark overlap are not checked.",
            "This sample does not establish the distribution of the complete dataset.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Output must differ from input")
    report = audit(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("rows", "limitations")}, indent=2))


if __name__ == "__main__":
    main()
