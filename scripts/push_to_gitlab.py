#!/usr/bin/env python3
"""
push_to_gitlab.py — 推送变更到 GitLab main 分支

用法：
    py -3 scripts/push_to_gitlab.py
    py -3 scripts/push_to_gitlab.py --commit-msg "feat: add firecrawl integration"
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = [sys.executable]


def run(cmd, cwd=None):
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=cwd or str(ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERR: {result.stderr}", file=sys.stderr)
        return False, result.stderr
    print(f"  OUT: {result.stdout[:200]}")
    return True, result.stdout


def main():
    ap = argparse.ArgumentParser(description="Push to GitLab main branch")
    ap.add_argument("--commit-msg", default="feat: integrate Firecrawl for Web3 news scraping")
    ap.add_argument("--skip-push", action="store_true", help="Only commit, don't push")
    args = ap.parse_args()

    print(f"Working directory: {ROOT}")

    # Check git status
    ok, out = run(["git", "status", "--short"])
    if not ok:
        print("Failed to get git status", file=sys.stderr)
        return 1
    print(out)

    # Add all changes
    ok, out = run(["git", "add", "."])
    if not ok:
        return 1

    # Check if there are changes to commit
    ok, out = run(["git", "diff", "--cached", "--stat"])
    if not ok:
        return 1
    if "no changes" in out.lower():
        print("No changes to commit")
        return 0

    # Commit
    ok, out = run(["git", "commit", "-m", args.commit_msg])
    if not ok:
        return 1

    # Pull rebase (avoid conflicts)
    ok, out = run(["git", "pull", "--rebase", "origin", "main"])
    if not ok:
        print("Pull failed, check for conflicts", file=sys.stderr)
        return 1

    # Push
    if not args.skip_push:
        ok, out = run(["git", "push", "origin", "main"])
        if not ok:
            print("Push failed", file=sys.stderr)
            return 1
        print("Successfully pushed to origin/main")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
