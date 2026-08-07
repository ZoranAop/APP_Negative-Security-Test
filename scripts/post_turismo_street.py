"""Fetch turismo street photography + post with Chinese nicknames (no 星/月)."""
import csv, json, os, re, sys, time, requests
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import config
from utils import log_info, log_success, log_error

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# 5 Chinese users (no 星/月 in name)
ACCOUNTS = [
    {"email": "u_dal8fpft@xxai.com", "password": "MeLGdghdbE6d", "nickname": "李晚霞"},
    {"email": "u_3xpisunq@xxai.com", "password": "HWYrLF51NRnZ", "nickname": "赵流年"},
    {"email": "u_ayvyepx7@xxai.com", "password": "KBvSUWuMazdA", "nickname": "范竹风"},
    {"email": "u_10g69xve@xxai.com", "password": "NYf1S3rKii1E", "nickname": "万初晴"},
    {"email": "u_2d0ypcd1@xxai.com", "password": "SWHqUm29nvki", "nickname": "邓清风"},
]

# Fetch one image per column from turismo
COLUMNS = ["cosplay"]
BASE = "https://www.turismo.cc"

def _get(url, ref):
    r = requests.get(url, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": ref})
    r.raise_for_status()
    return r.text

def fetch_turismo_images():
    images = []
    seen = set()
    for col in COLUMNS:
        try:
            txt = _get(f"{BASE}/{col}/", f"{BASE}/")
            slugs = re.findall(r'href="/([A-Za-z0-9]{5,8})\.html"', txt)
            if not slugs:
                continue
            for slug in slugs[:3]:
                if slug in seen: continue
                seen.add(slug)
                try:
                    detail = _get(f"{BASE}/{slug}.html", f"{BASE}/")
                    i = detail.find('id="post_content"')
                    if i < 0: continue
                    end = detail.find('class="related', i)
                    if end < 0: end = detail.find('id="footer"', i)
                    seg = detail[i: end if end > 0 else len(detail)]
                    urls = re.findall(r'(?:data-original|src)="(//img\.youwushow\.top/[^"]+\.(?:jpg|jpeg|png|webp))"', seg, re.I)
                    for u in urls:
                        full = "https:" + u
                        if "/dy_img_" not in full and full not in [im for im, _ in images]:
                            images.append((full, col))
                            break
                except Exception:
                    continue
                if len(images) >= 5:
                    break
            if len(images) >= 5:
                break
        except Exception as e:
            log_error(f"  {col}: {e}")
    return images[:5]

def login(email, password):
    r = requests.post(config.LOGIN_URL, json={"email": email, "password": password},
                      headers={"Content-Type": "application/json"}, timeout=15)
    if r.status_code == 200 and r.json().get("code") == 0:
        return r.json()["data"]["token"]
    return None

def s3_creds(token):
    for attempt in range(3):
        try:
            r = requests.post(config.UPLOAD_CREDENTIALS_URL,
                headers={"Authorization": f"Bearer {token}"}, timeout=15)
            if r.status_code == 200 and r.json().get("code") == 0:
                return r.json()["data"]
        except Exception:
            time.sleep(2)
    return None

def upload(url, creds):
    import boto3
    local = ROOT / "images" / f"turismo_{url.split('/')[-1][:20]}.jpg"
    local.parent.mkdir(exist_ok=True)
    if not (local.exists() and local.stat().st_size > 0):
        ref = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}/"
        r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0", "Referer": ref})
        if r.status_code != 200 or len(r.content) == 0:
            return None
        local.write_bytes(r.content)
    s3 = boto3.client("s3", aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        aws_session_token=creds["session_token"],
        region_name=creds.get("region", "ap-northeast-1"))
    k = f"square/original/{time.strftime('%Y/%m/%d')}/{local.name}"
    s3.upload_file(str(local), creds["bucket"], k,
        ExtraArgs={"ContentType": "image/jpeg", "CacheControl": "public, max-age=31536000, immutable"})
    return f"https://{creds.get('domain','teststatic-x.tp-ex.com')}/{k}"

def post_moment(token, txt, urls):
    p = {"content": txt, "visibility": 0}
    p["media_info"] = {"type": "image", "images": urls} if urls else {"type": "text"}
    for attempt in range(3):
        try:
            r = requests.post(config.MOMENTS_API_URL, json=p,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, timeout=30)
        except Exception:
            time.sleep(3); continue
        if r.status_code in (200, 201) and r.json().get("code") == 0:
            return True, r.json()["data"].get("moment_id", "?")
        if r.status_code == 429 or 500 <= r.status_code < 600:
            time.sleep(3 * (2**attempt)); continue
        return False, f"HTTP {r.status_code}"
    return False, "exhausted"

# Captions - Traditional Chinese, street photography
CAPTIONS = [
    "下午的陽光穿過行道樹，灑在人行道上剛剛好。路過的人都成了我的模特，按下快門的那一刻，時間好像停住了。📷 #街拍 #午後光影 #城市漫步",
    "鬧市區的十字路口是最佳觀景台，每個擦肩而過的人都有自己的故事。今天運氣不錯，捕捉到一個完美的回眸瞬間。✨ #街拍日常 #都市寫真 #隨手拍",
    "咖啡店的落地窗倒映著街景，裡面的客人和外面的行人重疊在一起，像一幅流動的畫。這種構圖可遇不可求。☕ #街拍攝影 #城市角落 #生活美學",
    "傍晚的商業街開始熱鬧起來，霓虹燈一盞盞亮起。站在天橋上往下看，車流和人群交織成這座城市最真實的脈搏。🌆 #暮色街拍 #城市夜景 #街頭風格",
    "一整天的拍攝結束了，翻看記憶卡裡的畫面，最喜歡的還是那張不經意拍到的背影。有時候最好的照片，就是最自然的那一瞬間。📸 #街拍日記 #城市隨筆 #記錄生活",
]

def main():
    log_info("=" * 60)
    log_info("  turismo 街拍 — 5帖 (1720池，繁體中文，無星/月)")
    log_info("=" * 60)

    log_info("\n[Phase 0] 獲取 turismo 圖片")
    images = fetch_turismo_images()
    log_info(f"  got {len(images)} images from {len(set(c for _,c in images))} columns")
    for i, (url, col) in enumerate(images):
        log_info(f"    [{i+1}] {col}: {url[:70]}...")
    if len(images) < 5:
        log_error("  not enough images"); return 1

    log_info("\n[Phase 1] 登錄")
    tokens = {}
    for i, a in enumerate(ACCOUNTS):
        log_info(f"  [{i+1}/5] {a['nickname']} ...")
        t = login(a["email"], a["password"])
        if t: tokens[i] = t; log_success("    OK")
        else: log_error("    FAIL")
        if i < 4: time.sleep(2.5)
    if not tokens: return 1

    log_info("\n[Phase 2] S3 上傳")
    cr = s3_creds(tokens[list(tokens.keys())[0]])
    if not cr: return 1
    s3_urls = []
    for i, (url, col) in enumerate(images):
        log_info(f"  [{i+1}/5] uploading ...")
        s3u = upload(url, cr)
        if s3u: s3_urls.append(s3u); log_success(f"    OK")
        else: log_error(f"    FAIL")
    if len(s3_urls) < 5: return 1

    log_info("\n[Phase 3] 發佈")
    for i in range(5):
        if i not in tokens: continue
        log_info(f"  [{i+1}/5] {ACCOUNTS[i]['nickname']} ...")
        ok, pid = post_moment(tokens[i], CAPTIONS[i], [s3_urls[i]])
        if ok: log_success(f"    OK → {pid}")
        else: log_error(f"    FAIL: {pid}")
        if i < 4: time.sleep(5)

    log_success("\nDone!")

if __name__ == "__main__":
    main()
