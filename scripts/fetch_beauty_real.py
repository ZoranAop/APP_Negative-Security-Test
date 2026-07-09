#!/usr/bin/env python3
"""
fetch_beauty_real.py — 从 opennana 采集「真人」少女/美女/女友/模特 视频, 排除卡通/动漫。

在 opennana_fetch.py 基础上加强:
  * 排除动漫/卡通/CG/3D 渲染/机甲等非真人内容(REAL_BLOCK 关键词, 命中即弃)
  * 要求命中真人少女/美女/女友/模特主题(GIRL_KEYWORDS)
  * 文案 = 标题 + 提示词提炼(build_caption 合并 title 与 prompt 关键信息)
  * 尊重 dedupe-file(已发过的 slug 跳过, 新选中的写回)

产出 CSV 列与 opennana_fetch.py 一致(post_room_video.py 可直接消费):
  content, visibility, room_id, image_urls, location_*, _video_url, _cover_url
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

OPENNANA_API_BASE = os.getenv("OPENNANA_API_BASE", "https://api.opennana.com")
HEADERS = {
    "User-Agent": os.getenv(
        "OPENNANA_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ),
    "Referer": os.getenv("OPENNANA_REFERER", "https://opennana.com/"),
    "Accept": "application/json",
}

# 真人少女/美女/女友/模特 主题(命中其一才要)。lowercase 子串, 匹配 标题+提示词+标签。
GIRL_KEYWORDS = [
    "woman", "girl", "female", "lady", "model", "fashion", "editorial",
    "portrait", "selfie", "bride", "girlfriend", "beauty", "goddess",
    "qipao", "dress", "makeup", "skin", "actress", "influencer", "streamer",
    "少女", "美女", "女友", "女性", "模特", "女生", "女神", "写真",
    "旗袍", "穿搭", "少妇", "御姐", "网红", "主播", "闺蜜", "姐姐", "美人",
]

# 动漫/卡通/CG/3D/非真人 -> 命中即弃(优先级高于 GIRL_KEYWORDS)
REAL_BLOCK = [
    "anime", "cartoon", "manga", "comic", "cg ", " cg", "cgi",
    "3d render", "3d-render", "rendered", "illustration", "illustrated",
    "cel-shad", "cel shad", "chibi", "vtuber", "pixar", "disney",
    "unreal engine", "octane", "blender", "stylized", "toon",
    "genshin", "gojo", "sukuna", "jujutsu", "naruto", "one piece",
    "mecha", "robot", "cyborg", "monster", "creature", "dragon",
    "动漫", "卡通", "漫画", "二次元", "厚涂", "插画", "手绘", "国漫",
    "机甲", "机器人", "怪物", "龙", "玄幻", "召唤", "赛博",
    "watercolor", "oil painting", "sketch", "vector art",
    # 非真人美女主题的其他排除项
    "cat", "kitten", "dog", "puppy", "bunny", "animal", "pet",
    "猫", "狗", "兔", "动物", "宠物",
    "funny", "comedy", "meme", "搞笑", "喜剧", "反转", "整活",
    "horror", "scary", "ghost", "zombie", "恐怖", "惊悚", "鬼", "诡异",
    "painting", "gallery", "画中", "油画", "画廊",
    "bicycle", "car ", "porsche", "lamborghini", "单车", "汽车", "跑车", "带货", "清仓",
    "kung fu", "wuxia", "武侠", "港片", "邵氏",
    # 更多非美女主题
    "santa", "christmas", "圣诞",
    "speaker", "bluetooth", "product", "gadget", "device", "音箱", "产品", "数码",
    "ninja", "warrior", "battle", "fight", "combat", "armor", "cosplay",
    "忍者", "战士", "激战", "剑斗", "铠甲", "格斗", "打斗",
    "money", "dollar", "bill", "currency", "carousel", "钞票", "美元", "货币", "旋转木马",
    "assassin", "kill", "暗杀", "暗影", "华尔兹",
    # 教程/演讲/科幻 等非美女主题
    "guru", "speech", "speaker ", "motivational", "success", "成功学", "演讲", "洗脑", "大师",
    "prompt", "json", "tutorial", "architecture", "提示词", "教程", "工程",
    "alien", "astronaut", "sci-fi", "sci fi", "space", "crystalline", "外星", "宇航", "科幻", "异变",
    "steel", "train", "shinkansen", "钢铁", "新干线", "高铁",
]

# 强主题白名单: 命中其一直接判定为真人美女(用于收紧误杀), 但仍需先过 REAL_BLOCK
STRONG_GIRL = [
    "少女", "美女", "女友", "女神", "模特", "写真", "旗袍", "穿搭", "自拍",
    "婚纱", "纯欲", "御姐", "闺蜜", "portrait", "editorial", "fashion model",
    "girlfriend", "bride", "wedding", "selfie", "goddess", "qipao",
]


def _s(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return " ".join(x for x in v if isinstance(x, str))
    return ""


def _prompt_text(detail: dict, cap: int = 1200) -> str:
    out = ""
    for p in detail.get("prompts") or []:
        out += _s(p.get("text") if isinstance(p, dict) else p) + " "
        if len(out) > cap:
            break
    return out[:cap]


def is_real_girl(detail: dict) -> bool:
    title = detail.get("title") or ""
    desc = (detail.get("description") or "")[:400]
    tags = _s(detail.get("tags"))
    model = (detail.get("model") or "")
    prompt = _prompt_text(detail)
    blob = (title + " " + desc + " " + tags + " " + model + " " + prompt).lower()
    if any(b in blob for b in REAL_BLOCK):
        return False
    # 优先: 命中强主题(少女/美女/模特/写真...) 直接通过
    if any(s.lower() in blob for s in STRONG_GIRL):
        return True
    return any(k.lower() in blob for k in GIRL_KEYWORDS)


# ---------------------------------------------------------------------------
# 文案: 发帖人第一人称口吻 + 干净话题标签(去 AI/模型类)
#   要求:
#     1. 以「发帖人自己」的角度陈述, 第一人称口吻(今天我… / 忍不住…)。
#     2. 在原提示词/标题的画面信息上升级, 更贴近真人分享的语气。
#     3. 话题标签只保留 2~3 个「发帖人关心的关键信息」(场景/穿搭/心情),
#        删除所有 AI / 模型 / 技术类标签(Seedance/提示词/超写实/电影感/4K…)。
# ---------------------------------------------------------------------------

# AI / 模型 / 生成技术 / 纯画质类词 —— 出现在标签里一律删除
AI_TAG_BLOCK = [
    "ai", "prompt", "seedance", "sora", "midjourney", "mj", "veo", "kling",
    "runway", "pika", "gen", "llm", "model", "diffusion", "stable",
    "提示词", "模型", "生成", "算法", "工程", "架构", "json",
    # 纯画质/摄制技术类(非发帖人会说的关键信息)
    "超写实", "写实", "电影感", "电影级", "运镜", "转场", "中心聚焦", "空间转场",
    "高饱和", "高清", "画质", "分辨率", "4k", "8k", "hd", "cg", "渲染", "特效",
    "cinematic", "photoreal", "ultra", "detailed", "render", "vfx",
]


def _clean_tag(t: str) -> bool:
    tl = t.lower().strip()
    if not tl:
        return False
    return not any(b in tl for b in AI_TAG_BLOCK)


# 场景 -> 发帖人第一人称模板(building on the prompt scene)。
# 每个场景配 2~3 个「发帖人关心」的干净标签。
_SCENE_RULES = [
    ("bride|wedding|婚纱|婚礼",
     "拍婚纱的那天，夕阳刚好落在我们身上，浪漫到想把这一刻永远留住",
     ["婚纱记录", "夕阳浪漫"]),
    ("bathroom|梳妆|浴室|vanity",
     "午后阳光斜斜地照进来，我慢慢梳妆，光影落在脸上那一刻真的好治愈",
     ["午后阳光", "梳妆日常"]),
    ("dessert|甜品|cafe|咖啡",
     "在甜品店转了一圈自拍，换了好几套造型，姐妹们觉得哪套最好看？",
     ["甜品店打卡", "换装自拍"]),
    ("encounter|偶遇|索吻|street.*kiss|求认识",
     "今天走在街上突然被人拦下想认识我，那一瞬间心跳都漏了一拍，好甜的偶遇",
     ["街头偶遇", "心动瞬间"]),
    ("rain|雨夜|雨|neon|霓虹",
     "雨夜的霓虹好美，我忍不住回眸拍了一段，胶片味儿的复古感谁懂啊",
     ["雨夜街拍", "回眸一笑"]),
    ("forest|森林|逆光|vintage|复古",
     "走进林子里拍了组逆光的照片，朦胧复古的光线把整个人都衬得好温柔",
     ["森林写真", "逆光复古"]),
    ("transform|变装|goddess|女神|纯欲|lazy.*home|居家",
     "从慵懒居家到精致出门，换装的这一刻感觉自己判若两人，超喜欢这种反差",
     ["居家变装", "反差穿搭"]),
    ("editorial|fashion|模特|杂志|hourglass|沙漏",
     "今天试了组杂志风的写真，多角度转了一圈，感觉自己也能当回封面模特啦～",
     ["模特写真", "时尚穿搭"]),
    ("selfie|自拍|snorricam|中心聚焦",
     "换了个角度拍自己，转到那一下的感觉真的绝，忍不住多看了几遍",
     ["换个角度", "时尚日常"]),
    ("travel|旅行|check-in|打卡",
     "拉着人一起出来旅行打卡，边走边换装边拍，这种松弛感太喜欢了",
     ["旅行打卡", "换装记录"]),
    ("beach|海边|泳|swim",
     "海边的风一吹整个人都放松下来了，随手一拍都是夏天的味道",
     ["海边日常", "夏日随拍"]),
    ("dance|舞|dancing|跳",
     "跟着音浪随便扭了两下，拍下来发现自己还挺上镜的嘛～",
     ["随手一拍", "氛围感"]),
]

_SCENE_COMPILED = [(re.compile(pat, re.I), tpl, tags) for pat, tpl, tags in _SCENE_RULES]

# 兜底模板(匹配不到具体场景时)
_FALLBACK = ("今天心情不错，随手记录了一段自己的小日常，分享给大家看看～",
             ["日常分享", "记录生活"])


def build_caption(detail: dict) -> str:
    """按发帖人第一人称口吻改写, 标签只留 2~3 个非 AI 关键信息。"""
    title = (detail.get("title") or "")
    tags = [t for t in (detail.get("tags") or []) if isinstance(t, str)]
    prompt = _prompt_text(detail, 800)
    blob = (title + " " + " ".join(tags) + " " + prompt)

    text, base_tags = _FALLBACK
    matched = False
    for rx, tpl, tg in _SCENE_COMPILED:
        if rx.search(blob):
            text, base_tags = tpl, tg
            matched = True
            break

    # 标签策略: 优先用场景模板自带的 2 个「发帖人关心」标签(已是干净词)。
    # 只有在没匹配到具体场景(兜底)时, 才尝试从源标签补 1 个干净标签凑够 2~3 个。
    picked = list(base_tags)
    if not matched:
        clean_src = [t for t in tags if _clean_tag(t)]
        for t in clean_src:
            if len(picked) >= 3:
                break
            if t not in picked:
                picked.append(t)
    picked = picked[:3]

    tagline = " ".join(f"#{t}" for t in picked)
    return f"{text} {tagline}".strip()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def list_prompts(page: int) -> list[dict]:
    r = requests.get(f"{OPENNANA_API_BASE}/api/prompts",
                     params={"media_type": "video", "page": page},
                     headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json().get("data")
    if isinstance(data, dict):
        return data.get("items") or []
    if isinstance(data, list):
        return data
    return []


def get_detail(slug: str) -> dict:
    r = requests.get(f"{OPENNANA_API_BASE}/api/prompts/{slug}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json().get("data") or r.json()


def load_dedupe(path: str | None) -> set[str]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
        if isinstance(d, list):
            return {str(x) for x in d}
        if isinstance(d, dict) and "slugs" in d:
            return {str(x) for x in d["slugs"]}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] read dedupe {path}: {e}", file=sys.stderr)
    return set()


def save_dedupe(path: str | None, seen: set[str]) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="采集真人少女/美女/女友/模特视频(排除动漫/卡通)")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--start-page", type=int, default=1)
    ap.add_argument("--max-pages", type=int, default=15)
    ap.add_argument("--dedupe-file", default="result/used_video_slugs.json")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    seen = load_dedupe(args.dedupe_file)
    print(f"[dedupe] 已发/已选 {len(seen)} 个 slug, 将跳过")
    picked: list[dict] = []
    picked_slugs: list[str] = []

    for page in range(args.start_page, args.start_page + args.max_pages):
        if len(picked) >= args.limit:
            break
        try:
            items = list_prompts(page)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] page {page}: {e}", file=sys.stderr)
            continue
        for it in items:
            if len(picked) >= args.limit:
                break
            slug = it.get("slug") or it.get("id")
            if not slug or str(slug) in seen:
                continue
            try:
                d = get_detail(str(slug))
            except Exception:  # noqa: BLE001
                continue
            videos = d.get("video_urls") or []
            images = d.get("images") or []
            if not videos:
                continue
            if not is_real_girl(d):
                continue
            cap = build_caption(d)
            picked.append({
                "content": cap,
                "visibility": 0,
                "room_id": "",
                "image_urls": "",
                "location_name": "", "location_address": "",
                "location_lat": "", "location_lon": "",
                "_video_url": videos[0],
                "_cover_url": images[0] if images else "",
                "_slug": str(slug),
                "_title": d.get("title") or "",
                "_model": d.get("model") or "",
            })
            picked_slugs.append(str(slug))
            print(f"[pick {len(picked)}] {slug}  model={d.get('model')}")
            print(f"        {cap[:70]}")
            time.sleep(0.15)

    if not picked:
        print("[warn] 未选到任何真人视频", file=sys.stderr)
        return 1

    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_video_url", "_cover_url"]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in picked:
            w.writerow({k: r.get(k, "") for k in fields})

    # 写回 dedupe(把新选中的 slug 合并进去, 避免下次再选)
    save_dedupe(args.dedupe_file, seen | set(picked_slugs))
    print(f"\n[OK] wrote {len(picked)} rows -> {out}")
    print(f"[OK] dedupe now {len(seen | set(picked_slugs))} slugs -> {args.dedupe_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
