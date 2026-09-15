#!/usr/bin/env python3
"""Retry the 13 comment accounts that failed with 429 during the main run.
Re-logs in with backoff and posts their pending comments."""
import json, glob, os, random, time, sys, requests, openpyxl
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
XLSX_670 = ROOT / "互动用户池_670账号.xlsx"
TOKENS_PATH = ROOT / "result" / "tokens.json"
LOGIN_URL = "https://api.xxai.com/login"
COMMENTS_API = "https://feed-api.xxai.com/api/v1/comments"

def load_tokens():
    if TOKENS_PATH.exists():
        try: return json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
        except: pass
    return {}

def login_backoff(email, pwd):
    for attempt in range(5):
        try:
            r = requests.post(LOGIN_URL, json={
                "email": email, "password": pwd,
                "device_id": "auto_poster", "device_name": "auto_poster_client"}, timeout=20)
            if r.status_code == 429:
                time.sleep(3.0 * (2 ** attempt)); continue
            if r.status_code == 200:
                j = r.json()
                if j.get("code") == 0:
                    return (j.get("data") or {}).get("token")
        except Exception:
            time.sleep(2)
    return None

# Load latest published + comments reports
pub_files = sorted(glob.glob(str(ROOT/"xhs_video_850_cmt_run"/"published_*.json")), key=os.path.getmtime)
cmt_files = sorted(glob.glob(str(ROOT/"xhs_video_850_cmt_run"/"comments_*.json")), key=os.path.getmtime)
pub = json.load(open(pub_files[-1], encoding="utf-8"))
cmt = json.load(open(cmt_files[-1], encoding="utf-8"))

# Rebuild the task list identically from the report (account -> moment, lang, text)
tasks = []
for r in cmt:
    if not r["status"].startswith("OK"):
        tasks.append({"account": r["account"], "moment": r["moment"],
                      "lang": r["lang"], "text": r["text"]})
print(f"retry {len(tasks)} failed comments")

# Load 670 pool to map nickname->email/password (dedupe by email)
wb = openpyxl.load_workbook(XLSX_670, read_only=True)
ws = wb.active
rows = list(ws.iter_rows(values_only=True)); wb.close()
acc_map = {}
for r in rows[1:]:
    email = str(r[1] or "").strip()
    nick = str(r[3] or "").strip()
    pwd = str(r[4] or "").strip()
    if email and pwd:
        acc_map[email] = {"nickname": nick, "password": pwd}
# Build nickname->email (first match; nicknames unique enough)
nick_to_email = {}
for email, v in acc_map.items():
    nick_to_email[v["nickname"]] = email

tokens = load_tokens()
success = 0
for i, t in enumerate(tasks):
    nick = t["account"]
    email = nick_to_email.get(nick, "")
    if not email:
        print(f"  [{i+1}/{len(tasks)}] {nick} no email found, skip")
        continue
    pwd = acc_map[email]["password"]
    tok = tokens.get(email)
    if not tok:
        tok = login_backoff(email, pwd)
    if not tok:
        print(f"  [{i+1}/{len(tasks)}] {nick} login still failing")
        continue
    try:
        r = requests.post(COMMENTS_API,
            json={"moment_id": int(t["moment"]), "content": t["text"]},
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            timeout=15)
        if r.status_code in (200, 201) and r.json().get("code") == 0:
            success += 1
            tokens[email] = tok
            print(f"  [{i+1}/{len(tasks)}] OK {nick} ({t['lang']}) → {t['moment']}")
        else:
            print(f"  [{i+1}/{len(tokens and 1 or 1)}] fail {nick}: {r.text[:50]}")
    except Exception as e:
        print(f"  [{i+1}/{len(tasks)}] exc {nick}: {e}")
    time.sleep(2.5 + random.uniform(0.5, 1.5))

# persist tokens
TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
TOKENS_PATH.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nretry done: {success}/{len(tasks)}")
