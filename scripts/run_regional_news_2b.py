#!/usr/bin/env python3
"""
run_regional_news_2b.py — Batch 2: concise news posts for
  - United States (EN)
  - Middle East / Gulf (EN)
  - Japan (JA)
  - South Korea (KO)
3 posts each = 12 total. Short, punchy, highlight-focused (no source attribution).
Fresh accounts from 670 pool.

Usage:
  py -3 scripts/run_regional_news_2b.py --yes
"""
from __future__ import annotations

import argparse, csv, io, json, subprocess, sys, time
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

INTERACT_XLSX = ROOT / "互动用户池_670账号.xlsx"
STATE_DIR = ROOT / "state"
DEDUPE_FILE = STATE_DIR / "seen_regional_news_2b.json"
CAPTION_DEDUPE = STATE_DIR / "seen_regional_news_2b_captions.json"

# (region, lang, topic, caption)  — concise, highlight-first
POSTS = [
    # ── United States — English ────────────────────────────────────────────
    (
        "us", "en", "politics",
        "The crypto bill is the thing to watch this session. If the framework clears the Senate, "
        "the entire US regulatory landscape changes overnight. That's the headline I'm watching.",
    ),
    (
        "us", "en", "tech",
        "US AI data-center buildout just hit a new scale. Compute supply is the constraint now, "
        "not demand. Whoever controls the next wave of capacity wins the decade.",
    ),
    (
        "us", "en", "web3",
        "RWA tokenization in the US went from pitch to production this quarter. "
        "Treasuries on-chain, real settlement, real institutions. That's the shift that matters.",
    ),

    # ── Middle East / Gulf — English ──────────────────────────────────────
    (
        "gulf", "en", "politics",
        "The Gulf is quietly becoming the new hub for capital and data centers. "
        "Sovereign funds are writing the next chapter, and the region is moving fast.",
    ),
    (
        "gulf", "en", "tech",
        "Gulf tech investment is no longer just oil money — it's a real R&D pipeline now. "
        "AI and semiconductor funds are deploying at a pace that surprised me.",
    ),
    (
        "gulf", "en", "web3",
        "Dubai and Abu Dhabi keep out-executing the rest of the region on crypto infrastructure. "
        "Clear licensing, real exchange presence, institutional on-ramps. The momentum is real.",
    ),

    # ── Japan — Japanese ──────────────────────────────────────────────────
    (
        "jp", "ja", "politics",
        "円安と金融政策の行方が今一番の注目点。日銀の次の方向性が株式と為替の両方に響いてくる。",
    ),
    (
        "jp", "ja", "tech",
        "日本の半導体とロボットが再加速している。国内生産基盤の再建とAI活用の両立がここ数年の勝負所。",
    ),
    (
        "jp", "ja", "web3",
        "日本のCrypto規制はようやく方向性が出た。金融庁の枠組みが明確になって、実務的な上陸路ができた印象。",
    ),

    # ── South Korea — Korean ──────────────────────────────────────────────
    (
        "kr", "ko", "politics",
        "국내 반도체 정책이 핵심입니다. 정부 지원과 수출 규제 변수가 다음 분기 흐름을 좌우할 것 같아요.",
    ),
    (
        "kr", "ko", "tech",
        "한국 AI 산업이 빠르게 성장 중입니다. 대기업은 물론 스타트업까지 반도체·AI에 대규모 투자하고 있죠.",
    ),
    (
        "kr", "ko", "web3",
        "한국 크립토 규제 방향이 조금씩 명확해지고 있습니다. 기관 진입 경로가 열리기 시작했다는 느낌이에요.",
    ),
]


def _load_used_emails():
    used = set()
    try:
        used.update(json.loads((ROOT / "result" / "tokens.json").read_text(encoding="utf-8")).keys())
    except Exception:
        pass
    for d in ROOT.glob("*_run"):
        for f in d.glob("accounts_merged_*.csv"):
            try:
                for row in csv.DictReader(open(f, encoding="utf-8-sig")):
                    e = (row.get("邮箱") or row.get("email") or "").strip().lower()
                    if e:
                        used.add(e)
            except Exception:
                pass
    return used


def load_accounts(n: int, exclude: set) -> list:
    import openpyxl
    if not INTERACT_XLSX.exists():
        print(f"[ERROR] {INTERACT_XLSX} not found", file=sys.stderr)
        return []
    wb = openpyxl.load_workbook(INTERACT_XLSX, read_only=True)
    ws = wb.active
    raw_rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not raw_rows:
        return []
    headers = [str(h or "") for h in raw_rows[0]]
    picked, seen = [], set(exclude)
    for row in raw_rows[1:]:
        if len(picked) >= n:
            break
        rd = dict(zip(headers, row))
        email = str(rd.get("邮箱", "") or "").strip()
        if not email or email in seen:
            continue
        seen.add(email)
        picked.append({
            "email": email,
            "password": str(rd.get("密码", "") or "").strip(),
            "pincode": str(rd.get("pincode", "") or "").strip(),
            "nickname": str(rd.get("昵称", "") or "").strip(),
            "seq": str(rd.get("序号", "") or "").strip(),
        })
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="regional_news_2b_run")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(exist_ok=True)

    used = _load_used_emails()
    accounts = load_accounts(len(POSTS), used)
    print(f"[accounts] {len(accounts)} fresh from 互动用户池_670:")
    for i, a in enumerate(accounts):
        print(f"  [{i+1}] {a['nickname']} ({a['email']})")

    used_caps = set()
    if CAPTION_DEDUPE.exists():
        try:
            used_caps = set(json.loads(CAPTION_DEDUPE.read_text(encoding="utf-8")))
        except Exception:
            pass

    moments = []
    for i, (region, lang, topic, caption) in enumerate(POSTS):
        if caption in used_caps:
            continue
        used_caps.add(caption)
        moments.append({
            "content": caption, "visibility": "0", "room_id": "",
            "image_urls": "", "location_name": "", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_lang": lang, "_source": f"regional2b_{region}_{topic}",
            "_topic": topic, "_dedupe_key": f"r2b_{region}_{topic}_{i}",
        })

    moments_csv = wd / f"moments_regional_news_2b_{ts}.csv"
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_lang", "_source", "_topic", "_dedupe_key"]
    with moments_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow(m)

    lang_count = {}
    for m in moments:
        lang_count[m["_lang"]] = lang_count.get(m["_lang"], 0) + 1
    print(f"\n[OK] {len(moments)} posts ready  lang_dist={lang_count}")
    for i, m in enumerate(moments):
        acct = accounts[i] if i < len(accounts) else {"nickname": "?"}
        print(f"  [{i+1}] {acct['nickname']:12} [{m['_source']:22}] | {m['content'][:45]}...")

    if not args.yes:
        if input("\nConfirm publish? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    CAPTION_DEDUPE.write_text(json.dumps(sorted(used_caps), ensure_ascii=False), encoding="utf-8")
    old = set()
    if DEDUPE_FILE.exists():
        try:
            old = set(json.loads(DEDUPE_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    DEDUPE_FILE.write_text(json.dumps(sorted(old | {m["_dedupe_key"] for m in moments}),
                                     ensure_ascii=False), encoding="utf-8")

    merged_acc = wd / f"accounts_merged_{ts}.csv"
    tokens_path = ROOT / args.tokens
    with merged_acc.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码", "pincode"])
        w.writeheader()
        for a in accounts[:len(moments)]:
            w.writerow({"序号": a["seq"], "昵称": a["nickname"],
                        "邮箱": a["email"], "密码": a["password"], "pincode": a["pincode"]})

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(merged_acc),
                "--csv", str(moments_csv),
                "--concurrency", str(args.concurrency),
                "--login-spacing", "3.0",
                "--record-dedupe",
                "--web3-dedupe-file", str(DEDUPE_FILE),
                "--skip-upload",
                "--tokens-out", str(tokens_path)]
    if tokens_path.exists():
        cmd += ["--tokens-in", str(tokens_path)]

    print(f"\n=== publishing {len(moments)} text-only posts ===")
    rc = subprocess.call(cmd, cwd=str(ROOT))
    print(f"Exit code: {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
