#!/usr/bin/env python3
"""devscan — scan ~/dev for git projects and sync the Hermes project dashboard.

Scans DEV_ROOT (default ~/dev) for directories containing a .git repo,
extracts per-project info (status, description, last commit), and merges
those entries into the Hermes project registry at ~/.hermes/scripts/projects.json.

Dev-scanned entries are tagged with "source": "devscan" so they can be
regenerated safely without touching hand-managed entries (flip, cost, etc.).

Usage:
    devscan                    Scan and show a preview (no changes)
    devscan --sync             Scan and write registry changes
    devscan --json             Print projects as JSON (after sync if --sync)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEV_ROOT = Path.home() / "dev"
REGISTRY = Path.home() / ".hermes" / "scripts" / "projects.json"
SOURCE_TAG = "devscan"

STATUS_ICONS = {"active": "🟢", "paused": "🟡", "done": "✅", "archived": "⚪"}


def run_git(repo: Path, *args: str) -> str:
    """Run a git command inside repo, returning stdout (stripped) or ''."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def repo_status(repo: Path) -> tuple[str, str]:
    """Return (status, last_commit_date) for a repo."""
    # Commit count: empty repo -> 0
    count = run_git(repo, "rev-list", "--count", "HEAD")
    if not count or count == "0":
        return "active", "no commits yet"
    last_ts = run_git(repo, "log", "-1", "--format=%at")
    if not last_ts:
        return "active", "unknown"
    last_dt = datetime.fromtimestamp(int(last_ts), tz=timezone.utc)
    age_days = (datetime.now(timezone.utc) - last_dt).days
    status = "active" if age_days <= 30 else "paused"
    return status, last_dt.strftime("%d %b %Y")


def repo_description(repo: Path) -> str:
    """Best-effort one-line description: README first non-heading line, else last commit."""
    for readme in (repo / "README.md", repo / "readme.md", repo / "Readme.md"):
        if readme.exists():
            for line in readme.read_text(errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("!"):
                    return line[:100]
    msg = run_git(repo, "log", "-1", "--format=%s")
    return msg[:100] if msg else "No description yet"


def scan_projects(dev_root: Path) -> list[dict]:
    """Scan dev_root for git repos and return project entries."""
    projects = []
    if not dev_root.is_dir():
        return projects
    for child in sorted(dev_root.iterdir()):
        if not child.is_dir() or (child / ".git").exists() is False:
            continue
        status, last = repo_status(child)
        projects.append({
            "name": child.name,
            "status": status,
            "description": repo_description(child),
            "last_commit": last,
            "source": SOURCE_TAG,
        })
    return projects


def load_registry() -> dict:
    if REGISTRY.exists():
        try:
            return json.loads(REGISTRY.read_text())
        except json.JSONDecodeError:
            print(f"⚠️  Registry unparseable: {REGISTRY}", file=sys.stderr)
            sys.exit(1)
    return {"projects": []}


def save_registry(data: dict) -> None:
    REGISTRY.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def merge(projects: list[dict], data: dict) -> tuple[list[dict], list[dict]]:
    """Merge scanned projects into registry. Returns (added, removed)."""
    existing = data.get("projects", [])
    scanned_names = {p["name"] for p in projects}

    kept = [e for e in existing if e.get("source") != SOURCE_TAG]
    added = [p for p in projects if p["name"] not in {e.get("name") for e in kept}]
    removed = [e for e in kept if e.get("source") == SOURCE_TAG and e["name"] not in scanned_names]  # legacy tag cleanup

    # Remove stale devscan entries that no longer exist on disk
    kept = [e for e in kept if not (e.get("source") == SOURCE_TAG and e["name"] not in scanned_names)]

    for p in projects:
        existing_other = next((e for e in kept if e.get("name") == p["name"]), None)
        if existing_other:
            existing_other.update({k: v for k, v in p.items() if k != "source"})
        else:
            kept.append(p)

    data["projects"] = kept
    return added, removed


def print_table(projects: list[dict]) -> None:
    if not projects:
        print("No dev projects found.")
        return
    w_name, w_status, w_desc = 18, 9, 60
    line = "┌" + "─" * (w_name + 2) + "┬" + "─" * (w_status + 2) + "┬" + "─" * (w_desc + 2) + "┐"
    print(line)
    print("│ " + "PROJECT".ljust(w_name) + " │ " + "STATUS".ljust(w_status) + " │ " + "DESCRIPTION".ljust(w_desc) + " │")
    print("├" + "─" * (w_name + 2) + "┼" + "─" * (w_status + 2) + "┼" + "─" * (w_desc + 2) + "┤")
    for p in projects:
        icon = STATUS_ICONS.get(p.get("status", "?"), "⚪")
        name = str(p.get("name", "?"))[:w_name]
        status = f"{icon} {p.get('status', '?')}"[:w_status]
        desc = str(p.get("description", ""))[: w_desc - 1] + ("…" if len(str(p.get("description", ""))) > w_desc - 1 else "")
        print(f"│ {name.ljust(w_name)} │ {status.ljust(w_status)} │ {desc.ljust(w_desc)} │")
    print("└" + "─" * (w_name + 2) + "┴" + "─" * (w_status + 2) + "┴" + "─" * (w_desc + 2) + "┘")


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan ~/dev and sync the project dashboard.")
    ap.add_argument("--sync", action="store_true", help="write registry changes")
    ap.add_argument("--json", action="store_true", help="print projects as JSON")
    ap.add_argument("--root", default=str(DEV_ROOT), help="directory to scan (default ~/dev)")
    args = ap.parse_args()

    dev_root = Path(args.root).expanduser()
    projects = scan_projects(dev_root)

    if args.json:
        print(json.dumps(projects, indent=2))
        return 0

    print(f"📂 devscan — {len(projects)} project(s) in {dev_root}")
    print_table(projects)

    if args.sync:
        data = load_registry()
        added, removed = merge(projects, data)
        save_registry(data)
        print(f"\n✅ Synced registry: +{len(added)} new, -{len(removed)} removed, {len(projects)} total dev projects.")
    else:
        print("\nPreview only — run `devscan --sync` to update the dashboard registry.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
