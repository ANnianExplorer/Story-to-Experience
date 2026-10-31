"""Offline documentation governance checks; no product validation claims."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit


def prose_and_fences(text: str) -> tuple[str, bool]:
    lines: list[str] = []
    opened: tuple[str, int] | None = None
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if match:
            marker, suffix = match.groups()
            if opened is None:
                opened = (marker[0], len(marker))
            elif marker[0] == opened[0] and len(marker) >= opened[1] and not suffix.strip():
                opened = None
            continue
        if opened is None:
            lines.append(line)
    return "\n".join(lines), opened is None


def anchors(text: str) -> set[str]:
    result: set[str] = set()
    counts: dict[str, int] = {}
    for line in prose_and_fences(text)[0].splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        value = match.group(1).lower().replace("`", "")
        value = "".join(c for c in value if c in " -_" or unicodedata.category(c)[0] in "LN")
        value = value.replace(" ", "-")
        n = counts.get(value, 0)
        counts[value] = n + 1
        result.add(value if n == 0 else f"{value}-{n}")
    return result


def check(root: Path) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    roots = [root / name for name in ("README.md", "AGENTS.md", "CLAUDE.md")]
    def repository_files(extension: str) -> list[Path]:
        found: list[Path] = []
        for name in ("docs", "packages", "apps"):
            for folder, directories, files in os.walk(root / name):
                directories[:] = [d for d in directories if d not in {"node_modules", ".npm-cache", ".git", "dist", "__pycache__"}]
                found.extend(Path(folder) / name for name in files if name.endswith(extension))
        return found

    md_files = sorted(set(roots + repository_files(".md")))
    texts: dict[Path, str] = {}
    link_count = 0
    for path in md_files:
        if not path.is_file():
            errors.append(f"Missing required document: {path.relative_to(root)}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            errors.append(f"Invalid UTF-8: {path.relative_to(root)}: {exc}")
            continue
        texts[path.resolve()] = text
        prose, balanced = prose_and_fences(text)
        if not balanced:
            errors.append(f"Unclosed code fence: {path.relative_to(root)}")
        for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", prose):
            target = target.strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            link_count += 1
            linked = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path.resolve()
            if not linked.exists():
                errors.append(f"Broken link: {path.relative_to(root)} -> {target}")
            elif parsed.fragment and linked.suffix.lower() == ".md":
                linked_text = linked.read_text(encoding="utf-8")
                if unquote(parsed.fragment) not in anchors(linked_text):
                    errors.append(f"Missing anchor: {path.relative_to(root)} -> {target}")

    for path in repository_files(".json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            errors.append(f"Invalid JSON: {path.relative_to(root)}: {exc}")

    registry_path = root / "docs/feature-registry.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        features = registry["features"]
        if registry["schema_version"] != 1 or not isinstance(features, list) or not features:
            raise ValueError("expected nonempty schema v1 registry")
    except (OSError, ValueError, KeyError) as exc:
        errors.append(f"Cannot load registry: {exc}")
        return errors, {"documents": len(texts), "links": link_count, "features": 0}

    known: set[str] = set()
    feature_ids: set[str] = set()
    graph: dict[str, list[str]] = {}
    for feature in features:
        try:
            fid = feature["id"]
            if not re.fullmatch(r"F\d{2}", fid) or fid in feature_ids:
                errors.append(f"Invalid/duplicate feature ID: {fid}")
            feature_ids.add(fid)
            graph[fid] = feature["dependencies"]
            if feature["design_status"] not in {"draft", "baseline", "superseded"}:
                errors.append(f"Invalid design status: {fid}")
            state = feature["implementation_status"]
            if state not in {"planned", "in_progress", "implemented", "verified", "released"}:
                errors.append(f"Invalid implementation status: {fid}")
            contents: dict[str, str] = {}
            for kind in ("sdd", "spec"):
                p = (root / feature[kind]).resolve()
                if not p.is_file():
                    errors.append(f"Missing {kind}: {fid}: {feature[kind]}")
                    contents[kind] = ""
                else:
                    contents[kind] = p.read_text(encoding="utf-8")
            reqs = set(feature["requirements"])
            if not reqs or len(reqs) != len(feature["requirements"]):
                errors.append(f"Empty/duplicate requirements: {fid}")
            task_coverage: set[str] = set()
            at_coverage: set[str] = set()
            for group, kind, label in ((feature["requirements"], "spec", "R"), (feature["tasks"], "sdd", "T"), (feature["acceptance"], "spec", "AT")):
                if not group:
                    errors.append(f"Empty {label} group: {fid}")
                for item in group:
                    identifier = item if isinstance(item, str) else item["id"]
                    if not re.fullmatch(fr"{fid}-{label}\d{{2}}", identifier) or identifier in known:
                        errors.append(f"Invalid/duplicate identifier: {identifier}")
                    known.add(identifier)
                    if not re.search(r"\b" + re.escape(identifier) + r"\b", contents[kind]):
                        errors.append(f"Identifier missing in {kind}: {identifier}")
                    if not isinstance(item, str):
                        mapped = set(item["requirements"])
                        if not mapped or not mapped <= reqs:
                            errors.append(f"Bad requirement mapping: {identifier}")
                        (task_coverage if label == "T" else at_coverage).update(mapped)
            if task_coverage != reqs or at_coverage != reqs:
                errors.append(f"Incomplete task/acceptance coverage: {fid}")
            for adr in feature["adrs"]:
                number = adr.removeprefix("ADR-")
                matches = list((root / "docs/adr").glob(f"{number}-*.md"))
                if len(matches) != 1 or adr not in matches[0].read_text(encoding="utf-8"):
                    errors.append(f"Unresolved ADR: {fid}: {adr}")
            for key in ("implementation_paths", "evidence"):
                paths = feature[key]
                for relative in paths:
                    if not (root / relative).exists():
                        errors.append(f"Missing {key}: {fid}: {relative}")
                needed = state in {"implemented", "verified", "released"} if key == "implementation_paths" else state in {"verified", "released"}
                if needed and not paths:
                    errors.append(f"Status {state} requires {key}: {fid}")
        except (KeyError, TypeError) as exc:
            errors.append(f"Malformed feature record: {feature.get('id', '?')}: {exc}")

    visited: set[str] = set()
    active: set[str] = set()

    def visit(fid: str) -> None:
        if fid in active:
            errors.append(f"Feature dependency cycle at {fid}")
            return
        if fid in visited:
            return
        active.add(fid)
        for dep in graph.get(fid, []):
            if dep not in feature_ids:
                errors.append(f"Unknown feature dependency: {fid} -> {dep}")
            else:
                visit(dep)
        active.remove(fid)
        visited.add(fid)

    for fid in graph:
        visit(fid)
    for path, text in texts.items():
        for identifier in set(re.findall(r"\bF\d{2}-(?:AT|T|R)\d{2}\b", text)):
            if identifier not in known:
                errors.append(f"Unknown ID in {path.relative_to(root)}: {identifier}")
    root_rules = texts.get((root / "CLAUDE.md").resolve(), "")
    gates = texts.get((root / "docs/quality/gates.md").resolve(), "")
    for i in range(1, 11):
        rid = f"R{i:02}"
        if rid not in root_rules or rid not in gates:
            errors.append(f"Unmapped root rule: {rid}")
    for i in range(1, 9):
        if f"G{i:02}" not in gates:
            errors.append(f"Missing gate: G{i:02}")
    return errors, {"documents": len(texts), "links": link_count, "features": len(features), "identifiers": len(known)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors, summary = check(args.root.resolve())
    print(json.dumps({"check": "documentation_governance", "status": "failed" if errors else "passed", **summary, "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
