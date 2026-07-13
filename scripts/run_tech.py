#!/usr/bin/env python3
"""
run_tech.py — 科技资讯一键发布（多源采集 → 按发帖人角色的第一人称文案 → 纯文本发布）

流程：
    1) 采集   fetch_tech.py    （8 个科技媒体各取 N 条，科技标签，纯文本）
    2) 文案   内置角色文案生成  （发帖人第一人称口吻，融入标题/摘要/来源，带 #科技 标签，全局不重复）
    3) 发布   publish_from_tokens.py （纯文本帖，media_info type=text）

用法：
    # 50 用户，每站 3 条（8 站=24 条），轮询分发
    py -3 scripts/run_tech.py --accounts-csv accounts_test_50.csv --num-accounts 50 --per-site 3 --yes

    # 只采集+文案预演
    py -3 scripts/run_tech.py --skip-publish
"""
from __future__ import annotations

import argparse
import csv
import random
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]
sys.path.insert(0, str(HERE))

from fetch_tech import ALL_SOURCES, SITE_CN  # noqa: E402

TAG = "科技"

# 发帖人角色 → 第一人称句式骨架。用 {title}{site}{tag} 组合，全局去重。
PERSONA_TEMPLATES = {
    "科技从业者": [
        "【{site}】{title}——从业者视角看，这条信息值得关注，行业风向又变了 {tag}",
        "刚看到{site}的报道：{title}。作为业内人，我觉得这透露出不少信号 {tag}",
        "{title}（via {site}）。这类进展对我们做技术的来说很有参考价值 {tag}",
    ],
    "科技爱好者": [
        "科技快讯｜{title}（来源：{site}）。作为数码控，这个我必须马克一下 {tag}",
        "看到{site}这条：{title}，越看越上头，科技迷狂喜 {tag}",
        "{title}——{site}报道。这波技术演进真的很有意思，分享给同好 {tag}",
    ],
    "投资观察者": [
        "【风向】{title}（{site}）。从投资角度看，这里面藏着机会与变量 {tag}",
        "{site}消息：{title}。盯赛道的朋友可以留意一下这条 {tag}",
        "值得记一笔｜{title}（via {site}），资本市场大概率会有反应 {tag}",
    ],
    "媒体观察员": [
        "今日科技｜{title}。{site}的这条报道信息量不小，转来一起看 {tag}",
        "帮大家划重点：{title}（来源：{site}）{tag}",
        "{title}——摘自{site}。一句话看懂今天的科技热点 {tag}",
    ],
}
PERSONA_ORDER = list(PERSONA_TEMPLATES.keys())


def _run(cmd, *, env_extra=None):
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def load_accounts(path: Path, n: int):
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))

    def pick(r, keys):
        for k in keys:
            if r.get(k):
                return r[k]
        return ""
    accts = []
    for r in rows:
        email = pick(r, ["邮箱", "email", "用户邮箱", "Email", "username"])
        pw = pick(r, ["密码", "password", "用户密码", "Password"])
        nick = pick(r, ["昵称", "用户昵称", "nickname", "nick"])
        if email and pw:
            accts.append({"email": email, "password": pw, "nick": nick})
    if n > 0 and len(accts) > n:
        accts = random.sample(accts, n)
    return accts


def persona_for(idx: int, nick: str) -> str:
    low = (nick or "").lower()
    if any(k in low for k in ("dev", "code", "tech", "工程", "程序", "技术")):
        return "科技从业者"
    if any(k in low for k in ("invest", "fund", "capital", "投", "基金", "股")):
        return "投资观察者"
    if any(k in low for k in ("media", "news", "编辑", "记者", "观察")):
        return "媒体观察员"
    return PERSONA_ORDER[idx % len(PERSONA_ORDER)]


def build_caption(item: dict, persona: str, *, seen: set) -> str:
    """按发帖人角色生成第一人称纯文本文案；与 seen 去重。"""
    title = (item.get("_title") or item.get("content") or "").strip()
    brief = (item.get("_brief") or "").strip()
    site = SITE_CN.get(item.get("_site", ""), item.get("_site", "科技媒体"))
    tag = f"#{TAG}"
    templates = PERSONA_TEMPLATES.get(persona) or next(iter(PERSONA_TEMPLATES.values()))

    order = list(range(len(templates)))
    random.shuffle(order)
    for ti in order:
        cap = templates[ti].format(title=title, site=site, tag=tag)
        # 有摘要时，30% 概率追加一句延伸，增加多样性且不超长
        if brief and len(cap) + len(brief) < 180 and random.random() < 0.4:
            cap = cap + f"｜{brief[:40]}"
        cap = cap.replace("  ", " ").strip()
        if cap not in seen:
            seen.add(cap)
            return cap
    # 兜底：加序号
    base = templates[0].format(title=title, site=site, tag=tag)
    i, cap = 2, base
    while cap in seen:
        cap = f"{base}（{i}）"
        i += 1
    seen.add(cap)
    return cap


def main() -> int:
    ap = argparse.ArgumentParser(
        description="tech news one-command publisher (fetch → role caption → text publish)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_test_50.csv")
    ap.add_argument("--sources", default=",".join(ALL_SOURCES))
    ap.add_argument("--per-site", type=int, default=3, help="每个网站取几条资讯")
    ap.add_argument("--num-accounts", type=int, default=50, help="选择的用户数量")
    ap.add_argument("--dedupe-file", default="state/seen_tech.json",
                    help="去重档（跨批次防重复资讯）")
    ap.add_argument("--reset-dedupe", action="store_true")
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--login-spacing", type=float, default=2.5)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="tech_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    raw = wd / f"tech_raw_{ts}.csv"
    moments = wd / f"moments_tech_{ts}.csv"

    acc_path = ROOT / args.accounts_csv
    if not acc_path.exists():
        print(f"[run_tech] 账号 CSV 不存在: {acc_path}", file=sys.stderr)
        return 2
    accts = load_accounts(acc_path, args.num_accounts)
    if not accts:
        print("[run_tech] 未能加载任何账号", file=sys.stderr)
        return 2
    n_sites = len([s for s in args.sources.split(",") if s.strip()])
    print(f"[run_tech] 选定 {len(accts)} 个用户；{n_sites} 个网站 × 每站 {args.per_site} 条 "
          f"= 目标 {n_sites * args.per_site} 条资讯（纯文本，#{TAG}）")

    # ---- Step 1: 采集 ----
    print("\n=== Step 1/3: 多源采集（科技媒体 → 标题/摘要，科技标签，纯文本）===")
    ded = ROOT / args.dedupe_file
    if args.reset_dedupe and ded.exists():
        ded.unlink()
        print(f"[run_tech] 已重置去重档：{ded.name}")
    cmd = PY + [str(HERE / "fetch_tech.py"),
                "--sources", args.sources, "--per-site", str(args.per_site),
                "--tag", TAG, "--dedupe-file", str(ded), "--output", str(raw)]
    if _run(cmd) != 0 or not raw.exists():
        print("[run_tech] 采集失败，终止。", file=sys.stderr)
        return 1

    items = list(csv.DictReader(raw.open(encoding="utf-8-sig")))
    # fetch_tech 用 content=title；补一个 _title 字段供文案用
    for it in items:
        it["_title"] = it.get("content", "")
    if not items:
        print("[run_tech] 未采集到任何资讯，终止。", file=sys.stderr)
        return 1
    print(f"[run_tech] 采集到 {len(items)} 条资讯")

    # ---- Step 2: 按发帖人角色生成文案（轮询对齐账号，全局不重复）----
    print("\n=== Step 2/3: 按发帖人角色生成第一人称文案（不重复）===")
    seen_caps: set[str] = set()
    rows = []
    for i, it in enumerate(items):
        acct = accts[i % len(accts)]
        persona = persona_for(i, acct["nick"])
        content = build_caption(it, persona, seen=seen_caps)
        rows.append({
            "content": content, "visibility": 0, "room_id": "", "image_urls": "",
            "location_name": "", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_site": it.get("_site", ""), "_tag": TAG, "_source": it.get("_source", ""),
        })
        print(f"  #{i+1} [{(acct['nick'] or acct['email'])[:14]} / {persona}] {content}")

    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_site", "_tag", "_source"]
    with moments.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[run_tech] moments 就绪：{len(rows)} 条 → {moments}")

    if args.skip_publish:
        print("\n[run_tech] --skip-publish，仅产出素材：", moments)
        return 0

    # ---- Step 3: 纯文本发布 ----
    print("\n=== Step 3/3: 发布（纯文本，media_info type=text）===")
    print(f"  账号 CSV : {acc_path}\n  素材条数 : {len(rows)}  并发: {args.concurrency}")
    if not args.yes:
        if input("  确认发布真实帖子？输入 y 继续：").strip().lower() not in ("y", "yes"):
            print("[run_tech] 已取消。素材已保存：", moments)
            return 0
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc_path), "--csv", str(moments),
                "--concurrency", str(args.concurrency),
                "--login-spacing", str(args.login_spacing),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd, env_extra={"POST_CROP_BOTTOM_HOSTS": ""})  # 纯文本无图，关闭裁切
    if rc != 0:
        print("[run_tech] 发布返回非零，请查看 result/ 报告。", file=sys.stderr)
        return rc
    print("\n[run_tech] 完成。发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
