#!/usr/bin/env python3
"""
run_x_video_publish_18.py — Download & publish 18 X/Twitter videos to XXAI Square.
Use fresh web3 accounts from pre_企管用户_850.csv.
One account per video, sequential login + S3 upload + publish.
"""
from __future__ import annotations

import argparse, csv, json, mimetypes, os, subprocess, sys, time, uuid
from pathlib import Path
from urllib.parse import urlparse

import requests
import boto3
from botocore.config import Config as BotoConfig

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

LOGIN_URL = os.getenv("LOGIN_URL", "https://api.xxai.com/login")
UPLOAD_URL = "https://api.xxai.com/file/upload/credentials"
PUBLISH_URL = "https://feed-api.xxai.com/api/v1/moments/"

# ─── 18 X video posts ─────────────────────────────────────────────────────
VIDEOS = [
    {
        "url": "https://x.com/YIYONG19680604/status/2099437054946074702/video/1",
        "caption": "这个处理乱插队的做法有点意思，文明出行靠规则，不靠吼。",
        "note_id": "x_yiyong_1",
    },
    {
        "url": "https://x.com/BagZuhre/status/2099420120703508835/video/1",
        "caption": "这个男人干的事，估计真要惹大麻烦了，现场反应也太快。",
        "note_id": "x_bagzuhre_2",
    },
    {
        "url": "https://x.com/FinWorld/status/2099698299641229379/video/1",
        "caption": "瑞幸最惨的时候，孙宇晨反手买了2%，如今浮盈超一亿美元。困境投资最难的地方，就是判断市场给出的死亡定价到底有没有过头——他赌瑞幸还能活下来，而且赌对了。",
        "note_id": "x_finworld_3",
    },
    {
        "url": "https://x.com/Alina_Lipp_X/status/2099382129226391590/video/1",
        "caption": "印度民众被普京抵达金砖峰会时跟空姐握手搞得不适应。这个动作是公开的，对方是女性，而且社会地位差距太大——这在印度文化里完全行不通。",
        "note_id": "x_alina_4",
    },
    {
        "url": "https://x.com/VOAChinese/status/2099565112524742802/video/1",
        "caption": "随着对AI潜在威胁的担忧不断加剧，英国国王查尔斯本周会见了英伟达、Google DeepMind、OpenAI和Anthropic的高管，讨论如何规范和引导AI的发展。",
        "note_id": "x_voa_5",
    },
    {
        "url": "https://x.com/altcap/status/2099573086354100364/video/1",
        "caption": "笑死：川普临时打进黄仁勋采访现场，全场哄堂大笑！黄仁勋正聊得起劲，总统来电。川普一句：『他能造出全世界最强AI芯片，却搞不定怎么把我放到免提上。』紧接着川普当场定性：机器人不会接管世界，AI末日论是骗局。美国不打算自己先刹车。",
        "note_id": "x_altcap_6",
    },
    {
        "url": "https://x.com/shaok45000/status/2099414742125449567/video/1",
        "caption": "苹果销售『给我一个不买苹果DUO的理由』的视频火了，已经有800万浏览。网友评价道：为什么要买一个暖宝宝。",
        "note_id": "x_shaok_7",
    },
    {
        "url": "https://x.com/rodriboero1986/status/2099735097708593645/video/1",
        "caption": "ACEPY CRITICA... también comentarios, propuestas, insultos y deseos buenos. Estoy tan positivo con tanta fe en Dios que nada me baja de donde ando. #builder #Web3 #argentina",
        "note_id": "x_rodri_8",
    },
    {
        "url": "https://x.com/bid_bits/status/2099381211244466287/video/1",
        "caption": "Security and multi-chain support matter in a TokenPocket clone script. Encryption protects data, while compatibility enables blockchain interaction.",
        "note_id": "x_bidbits_9",
    },
    {
        "url": "https://x.com/orange_web3/status/1801609901099389188/video/1",
        "caption": "Welcome to Orange, a Layer 1 blockchain focused on user-generated content (UGC) for Web3.",
        "note_id": "x_orange_10",
    },
    {
        "url": "https://x.com/BNBCHAIN/status/2099619202550358459/video/1",
        "caption": "Suits by day, padel by night. At RWA Summit 2026, we sat down with institutions and industry leaders to discuss the themes shaping the future of RWAs. Then we wrapped it up on the padel court — some of the best conversations happen off stage. 🎾",
        "note_id": "x_bnb_11",
    },
    {
        "url": "https://x.com/anoma/status/2097664611973513235/video/1",
        "caption": "Introducing @AnomaPay — Shielded Red Envelopes with @BNBCHAIN 🧧 Now there's a fun way to gift assets privately and onboard your friends and family to crypto. Perfect timing for Mid-Autumn Festival, but great year-round for any gifting occasion.",
        "note_id": "x_anoma_12",
    },
    {
        "url": "https://x.com/Bitget_zh/status/2097543548291965170/video/1",
        "caption": "8周年越来越近，有些期待，正在加速运算中 ⌛️ 第8年，如何过成你的「发」年？大声说出你的心仪资产，让极致交易在UEX起飞！投资股票就来Bitget，八方来财，一网打尽！",
        "note_id": "x_bitgetzh_13",
    },
    {
        "url": "https://x.com/Uniswap/status/2086868358197047542/video/1",
        "caption": "Earn is live on Uniswap Web App and Wallet. Deposit USDC, USDT, or ETH and put your assets to work in just a few steps.",
        "note_id": "x_uniswap_14",
    },
    {
        "url": "https://x.com/binance/status/2085396307464663434/video/1",
        "caption": "Gold. Silver. Trade both, settled in USDT. Your everything app for commodities.",
        "note_id": "x_binance_15",
    },
    {
        "url": "https://x.com/bitget/status/2097230893010330104/video/1",
        "caption": "Collecting the four UEX asset fragments: Crypto, Commodities, Metals, and US Stocks to unlock 600,000 USDT KCGI Treasure Map rewards. ⛏️🗺️",
        "note_id": "x_bitget_16",
    },
    {
        "url": "https://x.com/Motoswap/status/2099602020063977925/video/1",
        "caption": "Yield farming is back on Ethereum. CA: 0xBd965230588EAA536dE6aA45E8ebbc01638535e0 — https://motoswap.org",
        "note_id": "x_motoswap_17",
    },
    {
        "url": "https://x.com/Sony/status/2099489263154786665/video/1",
        "caption": "Awards season looks good on you, nominees ✨",
        "note_id": "x_sony_18",
    },
]


def _load_used_emails() -> set:
    used = set()
    try:
        used.update(json.loads((ROOT / "result" / "tokens.json").read_text(encoding="utf-8")).keys())
    except Exception:
        pass
    for d in ROOT.glob("x_video_*_run"):
        for f in d.glob("accounts_merged_*.csv"):
            try:
                for row in csv.DictReader(open(f, encoding="utf-8-sig")):
                    e = (row.get("邮箱") or row.get("email") or "").strip().lower()
                    if e:
                        used.add(e)
            except Exception:
                pass
    return used


def pick_accounts(n: int) -> list[dict]:
    used = _load_used_emails()
    picked = []
    seen = set(used)
    for csv_path in [ROOT / "pre_企管用户_850.csv"]:
        if not csv_path.exists():
            continue
        for r in csv.DictReader(open(csv_path, encoding="utf-8-sig")):
            email = (r.get("邮箱") or "").strip()
            if not email or email in seen:
                continue
            seen.add(email)
            picked.append(r)
            if len(picked) >= n:
                break
    return picked


def login_user(email: str, password: str) -> str:
    r = requests.post(LOGIN_URL,
        json={"email": email, "password": password,
              "device_id": "x_video_publisher", "device_name": "auto_poster_client"},
        headers={"Content-Type": "application/json"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    token = (data.get("data") or {}).get("token") or data.get("access_token") or data.get("token")
    if not token:
        raise RuntimeError(f"login fail: {data}")
    return token


def get_s3_creds(token: str) -> dict:
    r = requests.post(UPLOAD_URL, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("data") or data


def upload_to_s3(local_path: Path, creds: dict) -> str:
    today = time.strftime("%Y/%m/%d")
    key = f"square/original/{today}/{local_path.name}"
    content_type = mimetypes.guess_type(local_path.name)[0] or "video/mp4"
    s3 = boto3.client("s3",
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        aws_session_token=creds["session_token"],
        region_name=creds["region"],
        config=BotoConfig(signature_version="s3v4"),
    )
    s3.upload_file(str(local_path), creds["bucket"], key,
                  ExtraArgs={"ContentType": content_type})
    return f"https://{creds['domain']}/{key}"


def extract_thumbnail(local_video: Path, target_dir: Path, at_second: float = 0.5):
    """从视频抽 at_second 秒处的帧作为封面 jpg（仓库 video_pipeline.extract_thumbnail 逻辑）。
    ffmpeg 不可用或抽帧失败返回 None。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"{local_video.stem}_cover.jpg"
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None
    try:
        proc = subprocess.Popen(
            [ff, "-y", "-ss", str(at_second), "-i", str(local_video),
             "-frames:v", "1", "-q:v", "2", str(out_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        proc.communicate(timeout=60)
        if proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
            return out_path
        out_path.unlink(missing_ok=True)
        return None
    except Exception as e:
        print(f"    [thumb] 抽帧异常: {e}", file=sys.stderr)
        out_path.unlink(missing_ok=True)
        return None


def download_with_ytdlp(url: str, save_dir: Path, timeout: int = 180) -> tuple[Path | None, str | None]:
    save_dir.mkdir(parents=True, exist_ok=True)
    ts = uuid.uuid4().hex[:12]
    out = str(save_dir / f"x_vid_{ts}_%(id)s.%(ext)s")
    cmd = [sys.executable, "-m", "yt_dlp",
           "-f", "best[ext=mp4]/best",
           "-o", out,
           "--no-playlist", "--console-title",
           "--quiet", "--no-warnings",
           url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        files = list(save_dir.glob(f"x_vid_{ts}_*.mp4"))
        if r.returncode != 0 or not files:
            print(f"    yt-dlp rc={r.returncode} stderr: {r.stderr[-300:]}")
            return None, None
        return files[0], None
    except subprocess.TimeoutExpired:
        return None, None
    except Exception as e:
        print(f"    yt-dlp error: {e}")
        return None, None


def download_file(url: str, save_dir: Path, filename: str, timeout: int = 30) -> Path | None:
    save_dir.mkdir(parents=True, exist_ok=True)
    dst = save_dir / filename
    headers = {"User-Agent": UA, "Referer": "https://twitter.com/"}
    try:
        with requests.get(url, stream=True, headers=headers, timeout=timeout) as resp:
            resp.raise_for_status()
            with dst.open("wb") as f:
                for chunk in resp.iter_content(1 << 16):
                    f.write(chunk)
        return dst
    except Exception as e:
        print(f"    thumbnail download fail: {e}")
        return None


def publish_video(token: str, caption: str, video_url: str, thumbnail_url: str | None) -> dict:
    body = {
        "content": caption,
        "visibility": 0,
        "media_info": {
            "type": "video",
            "video_url": video_url,
            "thumbnail_url": thumbnail_url or video_url,
        },
    }
    r = requests.post(PUBLISH_URL,
        headers={"Authorization": f"Bearer {token}"},
        json=body, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"publish fail {r.status_code}: {r.text[:200]}")
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--login-spacing", type=float, default=3.0)
    ap.add_argument("--max-retries", type=int, default=3)
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / (args.workdir or f"x_video_18_{ts}_run")
    wd.mkdir(parents=True, exist_ok=True)
    media_dir = wd / "media"
    media_dir.mkdir(exist_ok=True)

    accounts = pick_accounts(len(VIDEOS))
    print(f"[accounts] {len(accounts)} fresh from pre_企管用户_850:")
    for i, a in enumerate(accounts):
        print(f"  [{i+1:2}] {a.get('昵称','?')} ({a.get('邮箱','?')})")

    if len(accounts) < len(VIDEOS):
        print(f"[WARN] only {len(accounts)} accounts available for {len(VIDEOS)} videos", file=sys.stderr)

    if not args.yes:
        if input(f"\nConfirm publish {len(VIDEOS)} videos? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled."); return 0

    results = []
    tokens_map = {}

    for i, v in enumerate(VIDEOS):
        acct = accounts[i % len(accounts)]
        email = acct["邮箱"].strip()
        nick = acct.get("昵称", "?")

        print(f"\n[{i+1}/{len(VIDEOS)}] {nick} ({email})")
        print(f"  url: {v['url'][:70]}")
        print(f"  cap: {v['caption'][:60]}...")

        try:
            token = None
            for retry in range(args.max_retries):
                try:
                    token = login_user(email, acct["密码"])
                    tokens_map[email] = token
                    print(f"  [1/5] Login OK")
                    break
                except Exception as e:
                    if retry < args.max_retries - 1:
                        wait = 8 * (retry + 1)
                        print(f"  [1/5] login fail ({e}), retry in {wait}s...")
                        time.sleep(wait)
                    else:
                        raise
            if not token:
                raise RuntimeError("login exhausted")

            creds = get_s3_creds(token)
            print(f"  [2/5] S3 creds OK")

            video_local, _ = download_with_ytdlp(v["url"], media_dir)
            if not video_local:
                raise RuntimeError("video download failed")
            size_mb = video_local.stat().st_size / (1024 * 1024)
            print(f"  [3/5] Video: {size_mb:.1f} MB")

            # 封面：从视频抽帧（ffmpeg 0.5s），失败回退 video_url
            cover_local = extract_thumbnail(video_local, media_dir, at_second=0.5)
            s3_video = upload_to_s3(video_local, creds)
            s3_thumb = s3_video
            if cover_local and cover_local.exists():
                s3_thumb = upload_to_s3(cover_local, creds)
                print(f"  [4/5] 封面抽帧 OK ({cover_local.stat().st_size//1024}KB)")
                cover_local.unlink(missing_ok=True)
            else:
                print(f"  [4/5] 抽帧失败，回退 video_url 作封面")

            result = publish_video(token, v["caption"], s3_video, s3_thumb)
            data = result.get("data") or {}
            moment_id = data.get("moment_id") or data.get("id") or "?"
            print(f"  [5/5] Publish OK → moment_id={moment_id}")

            results.append({"idx": i + 1, "user": nick, "email": email,
                           "moment_id": str(moment_id), "status": "OK", "url": v["url"]})
            video_local.unlink(missing_ok=True)

        except Exception as e:
            print(f"  [ERROR] {e}")
            results.append({"idx": i + 1, "user": nick, "email": email,
                           "moment_id": "", "status": f"FAIL: {e}", "url": v["url"]})

        if i < len(VIDEOS) - 1:
            time.sleep(args.login_spacing)

    (wd / "tokens.json").write_text(json.dumps(tokens_map, ensure_ascii=False, indent=2), encoding="utf-8")
    (wd / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for r in results if r["status"] == "OK")
    print(f"\n{'='*60}\nResults: {ok}/{len(results)} OK\n{'='*60}")
    for r in results:
        icon = "OK  " if r["status"] == "OK" else "FAIL"
        print(f"  [{r['idx']:2}] {icon} {r['user']:<15} moment_id={r['moment_id']}")
    print(f"\n[workdir] {wd}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
