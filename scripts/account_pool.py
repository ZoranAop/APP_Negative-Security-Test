"""
account_pool.py — Centralized account pool manager.

Source of truth:
  - 摄影师用户池: pre_企管用户_街拍摄影师.csv   (all photographer accounts)
  - Web3 用户池:   accounts_web3_100.csv       (derived from 互动用户池_100账号_完整信息.xlsx)
  - 互动用户池:    互动用户池_100账号_完整信息.xlsx / 互动用户池_220账号_完整信息.xlsx

Rules:
  1. Only read from the two source xlsx files + pre_企管用户_街拍摄影师.csv.
  2. All derived accounts_*.csv files are generated at runtime in run directories.
  3. Already-used emails are tracked via result/tokens.json + run-dir accounts_merged_*.csv.
  4. No accounts_*.csv files exist in the repo root except those actively referenced by scripts.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
TOKENS_FILE = ROOT / "result" / "tokens.json"
PHOTOGRAPHER_CSV = ROOT / "pre_企管用户_街拍摄影师.csv"
WEB3_CSV = ROOT / "accounts_web3_100.csv"  # if recreated from xlsx
INTERACT_100_XLSX = ROOT / "互动用户池_100账号_完整信息.xlsx"
INTERACT_220_XLSX = ROOT / "互动用户池_220账号_完整信息.xlsx"

EN_NICK_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-]*$")


def _is_en_nick(nick: str) -> bool:
    return bool(EN_NICK_RE.match(nick))


def _is_zh_nick(nick: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in nick)


def load_tokens() -> set[str]:
    if TOKENS_FILE.exists():
        try:
            return set(json.loads(TOKENS_FILE.read_text(encoding="utf-8")).keys())
        except Exception:
            pass
    return set()


def load_blocked() -> set[str]:
    blocked_file = ROOT / "state" / "blocked_emails.json"
    if blocked_file.exists():
        try:
            return set(json.loads(blocked_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def get_used_emails() -> set[str]:
    """Return emails already used in any previous photographer_opennana run."""
    used = set()
    for d in ROOT.glob("photographer_opennana_*_run"):
        for f in d.glob("accounts_merged_*.csv"):
            try:
                for row in csv.DictReader(open(f, encoding="utf-8-sig")):
                    used.add(row.get("邮箱", "").strip())
            except Exception:
                pass
    return used


def pick_photographer_accounts(n: int, exclude_emails: set[str] | None = None) -> list[dict]:
    """
    Pick n fresh EN-nick photographer accounts from pre_企管用户_街拍摄影师.csv.
    Excludes accounts already in tokens.json, blocked list, or previously used.
    """
    tokens = load_tokens()
    blocked = load_blocked()
    prev_used = get_used_emails()
    exclude = (exclude_emails or set()) | tokens | blocked | prev_used

    rows = list(csv.DictReader(open(PHOTOGRAPHER_CSV, encoding="utf-8-sig")))
    picked = []
    seen = set(exclude)
    for r in rows:
        email = r.get("邮箱", "").strip()
        nick = r.get("昵称", "")
        if email in seen:
            continue
        if _is_en_nick(nick):
            seen.add(email)
            picked.append(r)
            if len(picked) >= n:
                break
    return picked


def pick_web3_accounts(n: int, exclude_emails: set[str] | None = None) -> list[dict]:
    """
    Pick n web3 accounts from accounts_web3_100.csv (or pre pool if not exists).
    Falls back to pre_企管用户_街拍摄影师.csv EN-nick accounts if web3 pool unavailable.
    """
    tokens = load_tokens()
    blocked = load_blocked()
    prev_used = get_used_emails()
    exclude = (exclude_emails or set()) | tokens | blocked | prev_used

    source = WEB3_CSV if WEB3_CSV.exists() else PHOTOGRAPHER_CSV
    rows = list(csv.DictReader(open(source, encoding="utf-8-sig")))
    picked = []
    seen = set(exclude)
    for r in rows:
        email = r.get("邮箱", "").strip()
        nick = r.get("昵称", "")
        if email in seen:
            continue
        if _is_en_nick(nick):
            seen.add(email)
            picked.append(r)
            if len(picked) >= n:
                break
    return picked


def pick_interact_accounts(n: int, lang: str = "en",
                           exclude_emails: set[str] | None = None) -> list[dict]:
    """
    Pick n accounts from 互动用户池 (100 or 220 xlsx).
    lang='en' -> English nick; lang='zh' -> Chinese nick; lang='auto' -> mix.
    """
    tokens = load_tokens()
    blocked = load_blocked()
    exclude = (exclude_emails or set()) | tokens | blocked

    # Try 220 first, fall back to 100
    xlsx_files = [f for f in [INTERACT_220_XLSX, INTERACT_100_XLSX] if f.exists()]
    if not xlsx_files:
        return []

    picked = []
    seen = set(exclude)
    for xlsx in xlsx_files:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(xlsx, read_only=True)
            ws = wb.active
            headers = [cell.value for cell in ws[1]]
            for row in ws:
                if len(picked) >= n:
                    break
                row_dict = dict(zip(headers, row))
                email = str(row_dict.get("邮箱", "") or "").strip()
                nick = str(row_dict.get("昵称", "") or "")
                if email in seen:
                    continue
                if lang == "en" and _is_en_nick(nick):
                    seen.add(email)
                    picked.append(row_dict)
                elif lang == "zh" and _is_zh_nick(nick):
                    seen.add(email)
                    picked.append(row_dict)
                elif lang == "auto" and (_is_en_nick(nick) or _is_zh_nick(nick)):
                    seen.add(email)
                    picked.append(row_dict)
        except Exception:
            continue
        if len(picked) >= n:
            break
    return picked


def scan_root_account_csvs() -> list[dict]:
    """
    Scan all accounts_*.csv in root for EN-nick accounts that have valid tokens.
    Used as fallback when pool files are exhausted.
    """
    tokens = load_tokens()
    picked = []
    for f in sorted(ROOT.glob("accounts_*.csv")):
        try:
            for row in csv.DictReader(open(f, encoding="utf-8-sig")):
                email = row.get("邮箱", "").strip()
                nick = row.get("昵称", "")
                if email in tokens and _is_en_nick(nick):
                    picked.append(row)
        except Exception:
            pass
    return picked
