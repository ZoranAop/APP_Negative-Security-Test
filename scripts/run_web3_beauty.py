#!/usr/bin/env python3
"""
run_web3_beauty.py — web3 用户池发布「美女图 + 数字货币收益资讯」组合帖（图文）

1) 从 web3 用户池(accounts_web3_*.csv)选中文昵称用户（USED_EMAILS 记录已用，避免重复）
2) 采集数字货币增长/收益资讯（Google News 中文加密行情，正向关键词过滤 + 负向排除）
3) 生成生活化文案（简体评论池 → opencc 转繁体；去 AI 味、口语化、带生活细节 + emoji）
4) 图片来源：categories.json「美女」类单人物图（人物/画廊级去重，与美女标签任务共享账本）
5) 组合发帖：每帖 = 美女图 + 币圈收益资讯文案，发布（publish_from_tokens.py）

去重：资讯(state/seen_web3_beauty_news.json)、文案(state/seen_web3_beauty_captions.json)、
      图片(state/seen_photographer_beauty.json，与美女标签共享) 三层持久化去重。

用法:
    py -3 scripts/run_web3_beauty.py --num-accounts 5 --yes
    py -3 scripts/run_web3_beauty.py --num-accounts 5 --skip-publish
"""
from __future__ import annotations

import argparse
import csv
import glob
import html
import io
import json
import random
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import requests

try:
    from opencc import OpenCC
    _CC_S2T = OpenCC("s2t")
except Exception:  # noqa: BLE001
    _CC_S2T = None


def _to_hant(s: str) -> str:
    if _CC_S2T:
        try:
            return _CC_S2T.convert(s)
        except Exception:  # noqa: BLE001
            pass
    return s


# ---------------------------------------------------------------------------
# 美女图片去重（人物/画廊级，与美女标签任务共享账本，避免同一模特重复发图）
# ---------------------------------------------------------------------------
def _seed_ledgers() -> tuple[set, set]:
    """扫描 state/*.json 与 data/*.json 全部账本，返回 (used_urls, used_ids)。"""
    urls, ids = set(), set()
    files = sorted(set(glob.glob(str(ROOT / "state" / "*.json"))
                       + glob.glob(str(ROOT / "data" / "*.json"))))
    for p in files:
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        keys: list = []
        if isinstance(d, dict):
            keys += list(d.get("used_urls", []))
            keys += list(d.get("used", []))
            keys += list(d.get("urls", []))
            keys += list(d.get("ids", []))
            keys += list(d.get("slugs", []))
            keys += [k for k in d.get("pending", {}) if isinstance(k, str)]
        elif isinstance(d, list):
            keys = d
        for k in keys:
            if not isinstance(k, str):
                continue
            k = k.strip()
            if not k:
                continue
            if k.startswith("http"):
                urls.add(k)
            elif ":" in k or "/" in k:
                ids.add(k)
    return urls, ids


def _person_of_id(uid: str) -> str:
    parts = uid.split(":")
    if parts and parts[0] in ("yituyu", "turismo") and len(parts) >= 3:
        return f"{parts[0]}:{parts[1]}"
    return uid


def _person_of_url(url: str) -> str | None:
    m = re.search(r"img\.yituyu\.com/pic/(\d+)/", url)
    if m:
        return f"yituyu:{m.group(1)}"
    m = re.search(r"youwushow\.top/uploads/[^/]+/[^/]+/([^/]+)/", url)
    if m:
        return f"turismo:{m.group(1)}"
    return None


def _load_url_dedupe(path: Path) -> set:
    if not path.exists():
        return set()
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            return set(d.get("used_urls", []))
        if isinstance(d, list):
            return set(d)
    except Exception:
        pass
    return set()


def _save_url_dedupe(path: Path, urls: set) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"used_urls": sorted(urls)}, ensure_ascii=False, indent=2),
                    encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]
sys.path.insert(0, str(HERE))

from sources import collect_category, load_categories  # noqa: E402
from caption_dedupe import load_used_captions, save_used_captions  # noqa: E402

STATE_DIR = ROOT / "state"
DEDUPE_IMG = STATE_DIR / "seen_photographer_beauty.json"   # 美女图共享去重账本（与美女标签任务互通）
DEDUPE_NEWS = STATE_DIR / "seen_web3_beauty_news.json"
DEDUPE_CAP = STATE_DIR / "seen_web3_beauty_captions.json"

# 已用 web3 账号（避免重复发帖）
USED_EMAILS = {
    "u_31fepoh1@xxai.com", "u_2kn8kznb@xxai.com", "u_47livpw1@xxai.com",
    "u_3nzney7p@xxai.com", "u_2cs9t5g2@xxai.com",
    "u_bz6tak3e@xxai.com", "u_2mn6vlo4@xxai.com", "u_8f4ea5y5@xxai.com",
    "u_4h4beu38@xxai.com", "u_6l6gx9ba@xxai.com",
    "u_6szpcgbh@xxai.com", "u_3uk5hyy0@xxai.com",
    "u_5n8gjcbp@xxai.com", "u_5yyiefn8@xxai.com", "u_f0mgv5on@xxai.com",
    "u_5wqipk83@xxai.com", "u_77t19lwi@xxai.com",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# 数字货币增长/收益资讯查询词（中文）
GROWTH_QUERY = ("比特币 OR 以太坊 OR Solana OR 加密货币 OR 山寨币 "
                "涨 OR 突破 OR 新高 OR 飙升 OR 涨幅 OR 收益 OR 空投")

# 正向关键词（增长/收益，命中才保留）
GROWTH_KW = ["涨", "飙升", "突破", "新高", "涨幅", "上涨", "大涨", "创新高", "反弹",
             "走强", "上扬", "收益", "空投", "质押", "翻倍", "盈利", "利好", "攀升",
             "回暖", "增长", "激增", "上扬", "暴涨",
             "surge", "rally", "gain", "jump", "soar", "climb", "rise", "record",
             "breakout", "pump", "bullish", "profit", "yield", "airdrop", "staking",
             "all-time", "outperform", "top"]

# 负向关键词（下跌/风险，命中即弃）
NEG_KW = ["跌", "崩", "暴跌", "下跌", "重挫", "闪崩", "爆仓", "清算", "亏损", "诈骗",
          "黑客", "被盗", "违法", "调查", "起诉", "逮捕", "洗钱", "腰斩", "跳水",
          "crash", "plunge", "fall", "drop", "decline", "slump", "loss", "bear",
          "dump", "hack", "scam", "fraud", "arrest", "lawsuit", "ban", "delist",
          "suspend", "liquidat"]

# 生活化评论池（简体，去 AI 味，口语化、带个人生活细节）
LIFE_COMMENTS = [
    "睡醒一看又涨了，手里那点总算回本了",
    "想起上个月没上车，现在有点后悔",
    "这波涨得我都有点懵，账户总算好看了",
    "摸鱼刷到差点叫出声",
    "朋友昨天还问我要不要加仓，他眼光还行",
    "中午吃饭都在盯盘，谁顶得住啊",
    "看着爽，可惜我仓位太轻了",
    "昨晚还纠结要不要卖，还好忍住了",
    "家里人都说我看手机看魔怔了",
    "涨成这样，晚上得加个菜",
    "群里的老哥已经晒单了，我还在纠结",
    "持仓终于翻红了，敢跟家里说在搞这个了",
    "下班路上刷到，走路都带风了",
    "今天这行情，比工资到账还开心",
    "刷了一天盘，眼睛酸了也值了",
    "楼下大爷都开始问比特币了，这热度",
]

EMOJIS = ["🍗", "😅", "😮", "🤯", "👍", "🍚", "😭", "😮‍💨", "📱", "🍲",
          "🤔", "🙈", "🚶", "💸", "👀", "🔥"]


def _coin_tags(title: str) -> str:
    low = title.lower()
    if "以太" in title or "eth" in low:
        return "#以太坊 #ETH #web3"
    if "sol" in low:
        return "#Solana #SOL #web3"
    if "比特" in title or "btc" in low:
        return "#比特币 #BTC #web3"
    if "xrp" in low or "瑞波" in title:
        return "#XRP #瑞波 #web3"
    if "bnb" in low or "币安" in title:
        return "#BNB #币安 #web3"
    return "#加密货币 #web3"


def _gen_caption(title: str, used: set, rng: random.Random) -> str:
    """生活化文案：币种增长资讯 + 生活感慨 + 币种标签，去 AI 味、不重复、繁体中文。"""
    tags = _coin_tags(title)
    for _ in range(200):
        comment = rng.choice(LIFE_COMMENTS)
        emoji = rng.choice(EMOJIS)
        cap = _to_hant(f"{title}。{comment} {emoji} {tags}")
        if cap not in used:
            used.add(cap)
            return cap
    return _to_hant(f"{title}。{rng.choice(LIFE_COMMENTS)} {rng.choice(EMOJIS)} {tags}")


def _u8():
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:
        pass


def _is_chinese_nick(nick: str) -> bool:
    s = (nick or "").strip()
    return bool(re.search(r"[\u4e00-\u9fff]", s)) and not re.search(r"[\u3040-\u30ff]", s)


def load_web3_accounts() -> list[dict]:
    seen: dict[str, dict] = {}
    files = sorted(glob.glob(str(ROOT / "accounts_web3_*.csv")))
    for f in files:
        try:
            for r in csv.DictReader(open(f, encoding="utf-8-sig")):
                e = (r.get("邮箱") or "").strip()
                if e and e not in seen:
                    seen[e] = r
        except Exception:
            continue
    return list(seen.values())


def _clean_title(raw: str) -> str:
    t = html.unescape(raw or "")
    t = re.sub(r"<[^>]+>", "", t)
    for _ in range(3):
        prev = t
        t = re.sub(r"\s+-\s+[^-]+$", "", t).strip()
        if t == prev:
            break
    t = re.sub(r"\s*[|｜]\s*[^|｜]*$", "", t).strip()
    t = re.sub(r"^【[^】]*】\s*", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def fetch_growth_titles(want: int, used_norm: set) -> list[str]:
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(GROWTH_QUERY) +
           "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans")
    r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
    r.raise_for_status()
    txt = r.content.decode("utf-8", errors="ignore")
    items = re.findall(r"<item>(.*?)</item>", txt, re.S) or \
        re.findall(r"<entry>(.*?)</entry>", txt, re.S)
    out, seen = [], set(used_norm)
    for it in items:
        if len(out) >= want:
            break
        tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        title = _clean_title(tm.group(1) if tm else "")
        if len(title) < 8 or len(title) > 80:
            continue
        low = title.lower()
        if not any(k in low for k in GROWTH_KW):
            continue
        if any(k in low for k in NEG_KW):
            continue
        norm = re.sub(r"\s+", "", title.lower())
        if norm in seen:
            continue
        seen.add(norm)
        out.append(title)
    return out


def main() -> int:
    _u8()
    ap = argparse.ArgumentParser(description="web3 用户池发布美女图 + 数字货币收益资讯（组合发帖）")
    ap.add_argument("--num-accounts", type=int, default=5)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--login-spacing", type=float, default=2.5)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="web3_beauty_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    # ---- 1. 选 web3 中文昵称用户（避开已用）----
    accts = load_web3_accounts()
    zh = [a for a in accts
          if _is_chinese_nick(a.get("昵称") or "")
          and (a.get("邮箱") or "").strip() not in USED_EMAILS]
    n = min(args.num_accounts, len(zh))
    sel = zh[:n]
    print(f"[web3_beauty] web3 中文昵称用户（未用）{len(zh)} 个，选 {n} 个")
    for a in sel:
        print(f"    - {a.get('昵称')}")

    # ---- 2. 采集数字货币增长/收益资讯 ----
    print(f"\n=== Step 1/4: 采集数字货币增长/收益资讯（需 {n} 条）===")
    STATE_DIR.mkdir(exist_ok=True)
    used_norm = set()
    if DEDUPE_NEWS.exists():
        try:
            used_norm = set(json.loads(DEDUPE_NEWS.read_text(encoding="utf-8")))
        except Exception:
            pass
    titles = fetch_growth_titles(n * 4, used_norm)[:n]
    print(f"[web3_beauty] 增长资讯 {len(titles)} 条（需 {n}）")
    for t in titles:
        print(f"    - {t}")

    if len(titles) < n:
        print(f"[web3_beauty] 资讯不足，仅产出 {len(titles)} 条。", file=sys.stderr)

    # ---- 3. 生成生活化文案（去 AI 味）----
    print("\n=== Step 2/4: 生成生活化文案（口语化、去 AI 味）===")
    used_cap = load_used_captions(DEDUPE_CAP)
    rng = random.Random(int(time.strftime("%Y%m%d%H%M%S")))
    captions = []
    for i, t in enumerate(titles):
        cap = _gen_caption(t, used_cap, rng)
        captions.append(cap)
        print(f"    #{i+1} {cap[:80]}")

    # ---- 4. 采集美女图（来源不变，复用美女去重账本）----
    print(f"\n=== Step 3/4: 采集美女标签图片（需 {n} 张）===")
    seed_urls, seed_ids = _seed_ledgers()
    own_urls = _load_url_dedupe(DEDUPE_IMG)
    used_urls = seed_urls | own_urls
    used_ids = seed_ids
    used_persons = {_person_of_id(i) for i in used_ids}
    for u in used_urls:
        p = _person_of_url(u)
        if p:
            used_persons.add(p)

    def _id_used(i):
        return i in used_ids or _person_of_id(i) in used_persons

    def _url_used(u):
        return u in used_urls or bool(_person_of_url(u) and _person_of_url(u) in used_persons)

    cats = load_categories()
    beauty_srcs = cats.get("美女", {}).get("sources", [])
    cats["美女"]["sources"] = [s for s in beauty_srcs
                               if s.get("type") in ("yituyu", "turismo", "aituitu")]
    for s in cats["美女"]["sources"]:
        if s.get("type") == "yituyu":
            s["imgs_per_gallery"] = 1
        elif s.get("type") == "turismo":
            s["imgs_per_post"] = 1
    recs = collect_category("美女", max(n * 4, n + 8),
                            has_id=_id_used, has_url=_url_used, categories=cats)
    imgs, seen_person = [], set(used_persons)
    for r in recs:
        if len(imgs) >= n:
            break
        if r["url"] in used_urls:
            continue
        p = _person_of_id(r["id"]) or _person_of_url(r["url"])
        if p in seen_person:
            continue
        seen_person.add(p)
        imgs.append(r)
    print(f"[web3_beauty] 美女图 {len(imgs)} 张（需 {n}）")
    for r in imgs:
        print(f"    - [{r['site']}] {r['url'][:60]}")

    # ---- 组装 ----
    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    rows = []
    for i in range(min(len(imgs), len(captions))):
        rows.append({"content": captions[i], "image_urls": imgs[i]["url"],
                     "_source": "web3_beauty", "_site": imgs[i]["site"], "_lang": "zh_hant"})

    acc_out = wd / f"accounts_web3_beauty_{ts}.csv"
    with acc_out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["邮箱", "用户名", "昵称", "密码"])
        w.writeheader()
        for a in sel:
            w.writerow({"邮箱": a.get("邮箱", ""), "用户名": a.get("用户名", ""),
                        "昵称": a.get("昵称", ""), "密码": a.get("密码", "")})

    mom_csv = wd / f"moments_web3_beauty_{ts}.csv"
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_site", "_lang"]
    with mom_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    uniq = len(set(r["content"] for r in rows))
    print(f"[web3_beauty] 素材就绪：{len(rows)} 帖 → {mom_csv.name}（文案唯一 {uniq}/{len(rows)}）")

    # 回写去重
    used_norm |= {re.sub(r"\s+", "", t.lower()) for t in titles}
    DEDUPE_NEWS.write_text(json.dumps(sorted(used_norm), ensure_ascii=False, indent=2),
                           encoding="utf-8")
    save_used_captions(used_cap, DEDUPE_CAP)
    _save_url_dedupe(DEDUPE_IMG, used_urls | {r["image_urls"] for r in rows})

    if args.skip_publish:
        print("[web3_beauty] --skip-publish，仅产出素材。")
        return 0

    if not args.yes:
        if input(f"  确认发布真实帖子（{len(rows)} 帖）？输入 y 继续：").strip().lower() not in ("y", "yes"):
            print("[web3_beauty] 已取消。素材已保存。")
            return 0

    # ---- 发布 ----
    print("\n=== Step 4/4: 发布 ===")
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc_out),
                "--csv", str(mom_csv),
                "--concurrency", str(args.concurrency),
                "--login-spacing", str(args.login_spacing),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    import os
    e = os.environ.copy()
    e.setdefault("PYTHONIOENCODING", "utf-8")
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    rc = subprocess.call(cmd, cwd=str(ROOT), env=e)
    if rc != 0:
        print("[web3_beauty] 发布返回非零，请查看 result/ 报告。", file=sys.stderr)
        return rc
    print("\n[web3_beauty] 完成。发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
