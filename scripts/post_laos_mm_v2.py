"""老撾/緬甸街拍 v2 — 文案與圖片精準匹配（從採集 CSV 選圖）"""
import argparse, csv, hashlib, json, os, sys, time, boto3, requests
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from config import config
from utils import ensure_utf8_stdout, log_info, log_success, log_error

ensure_utf8_stdout()

LOGIN_URL = os.getenv("LOGIN_URL", "https://api.xxai.com/login")
UPLOAD_URL = os.getenv("UPLOAD_CREDENTIALS_URL", "https://api.xxai.com/file/upload/credentials")
MOMENTS_URL = os.getenv("MOMENTS_API_URL", "https://feed-api.xxai.com/api/v1/moments/")

DEFAULT_LAOS_CSV = "sea_run/laos_raw_20260805_093940.csv"
DEFAULT_MM_CSV = "sea_run/myanmar_raw_20260805_093942.csv"


def load_accounts(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return [{"email": (r.get("邮箱") or r.get("email") or "").strip(),
                 "password": (r.get("密码") or r.get("password") or "").strip(),
                 "nickname": (r.get("昵称") or r.get("nickname") or "").strip()}
                for r in csv.DictReader(f)]


def login(email, password):
    r = requests.post(LOGIN_URL, json={"email": email, "password": password,
        "device_id": "auto_poster", "device_name": "auto_poster_client"},
        headers={"Content-Type": "application/json"}, timeout=15)
    if r.status_code == 200 and r.json().get("code") == 0:
        return r.json()["data"]["token"]
    log_error(f"login FAIL: {r.json().get('msg','?')}")
    return None


def s3_creds(token):
    for _ in range(3):
        try:
            r = requests.post(UPLOAD_URL, headers={"Authorization": f"Bearer {token}"}, timeout=15)
            if r.status_code == 200 and r.json().get("code") == 0:
                return r.json()["data"]
        except Exception:
            pass
        time.sleep(2)
    return None


def upload_to_s3(image_url, creds):
    url_hash = hashlib.md5(image_url.encode()).hexdigest()[:12]
    local = ROOT / "images" / f"laos_mm_{url_hash}.jpg"
    local.parent.mkdir(exist_ok=True)
    if not (local.exists() and local.stat().st_size > 0):
        r = requests.get(image_url, timeout=60,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.pexels.com/"})
        if r.status_code != 200:
            raise RuntimeError(f"download fail {r.status_code}")
        local.write_bytes(r.content)
    s3 = boto3.client("s3", aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        aws_session_token=creds["session_token"],
        region_name=creds.get("region", "ap-northeast-1"))
    key = f"square/original/{time.strftime('%Y/%m/%d')}/{local.name}"
    s3.upload_file(str(local), creds["bucket"], key,
        ExtraArgs={"ContentType": "image/jpeg", "CacheControl": "public, max-age=31536000, immutable"})
    return f"https://{creds.get('domain','teststatic-x.tp-ex.com')}/{key}"


def post_moment(token, text, image_url):
    payload = {"content": text, "visibility": 0}
    if image_url:
        payload["media_info"] = {"type": "image", "images": [image_url]}
    for attempt in range(3):
        try:
            r = requests.post(MOMENTS_URL, json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, timeout=30)
        except Exception:
            time.sleep(3); continue
        if r.status_code in (200, 201) and r.json().get("code") == 0:
            return True, r.json()["data"].get("moment_id", "?")
        if r.status_code == 429 or 500 <= r.status_code < 600:
            time.sleep(3 * (2 ** attempt)); continue
        return False, r.json().get("msg", f"HTTP {r.status_code}")
    return False, "exhausted"


def main():
    ap = argparse.ArgumentParser(description="老撾/緬甸街拍（從採集CSV選圖+自定義文案）")
    ap.add_argument("--accounts-csv", required=True, help="攝影師账号 CSV")
    ap.add_argument("--laos-csv", default=DEFAULT_LAOS_CSV, help="老撾採集 CSV")
    ap.add_argument("--myanmar-csv", default=DEFAULT_MM_CSV, help="緬甸採集 CSV")
    ap.add_argument("--tokens-out", default=None, help="保存 token 的路徑")
    args = ap.parse_args()

    accounts = load_accounts(args.accounts_csv)
    if len(accounts) < 5:
        log_error(f"需要至少 5 個帳號，只有 {len(accounts)}")
        return 1
    accounts = accounts[:5]

    raw_laos = list(csv.DictReader(open(ROOT / args.laos_csv, encoding="utf-8-sig")))
    raw_mm = list(csv.DictReader(open(ROOT / args.myanmar_csv, encoding="utf-8-sig")))

    # 選圖 + 匹配繁體中文文案
    POSTS = [
        {"image_url": raw_laos[4]["image_urls"], "caption": "龍坡邦的街頭，色彩鮮豔的嘟嘟車停在路邊，車夫靠在座椅上打著盹。這座古城的節奏就是這麼慢，慢到讓人忘了時間。🛺 #老撾 #龍坡邦街拍 #城市生活", "desc": raw_laos[4]["content"]},
        {"image_url": raw_laos[5]["image_urls"], "caption": "清晨的龍坡邦，小沙彌們穿著橘色袈裟赤腳走過街頭，手捧缽盂接受信眾的供養。這種畫面每天都在上演，但每一次都讓人動容。🧡 #老撾 #布施 #人文紀實", "desc": raw_laos[5]["content"]},
        {"image_url": raw_laos[6]["image_urls"], "caption": "香通寺的午後很安靜，一位僧侶在佛像前靜靜祈禱。光影穿過木窗灑進來，整個空間彷彿被時間凝固了。🙏 #老撾 #香通寺 #旅行隨筆", "desc": raw_laos[6]["content"]},
        {"image_url": raw_mm[0]["image_urls"], "caption": "夜幕降臨後的仰光，蘇雷寶塔在車流光軌的襯托下閃耀著金色光芒。這座城市的夜晚有種獨特的魔力。🌃 #緬甸 #仰光夜景 #城市街拍", "desc": raw_mm[0]["content"]},
        {"image_url": raw_mm[3]["image_urls"], "caption": "蒲甘的希提羅明羅佛塔靜靜矗立在蓊鬱的綠意中，雲層壓得很低，給這座千年古塔增添了幾分神秘感。🛕 #緬甸 #蒲甘 #古蹟巡禮", "desc": raw_mm[3]["content"]},
    ]

    log_info("=" * 60)
    log_info("  老撾/緬甸街拍 v2 — 文案與圖片精準匹配")
    log_info("=" * 60)

    log_info("\n[Phase 1] 登錄")
    tokens = {}
    for i, a in enumerate(accounts):
        log_info(f"  [{i+1}/5] {a['nickname']} ... ")
        t = login(a["email"], a["password"])
        if t: tokens[i] = t; log_success("    OK")
        else: log_error("    FAIL")
        if i < 4: time.sleep(2.5)
    if len(tokens) < 5:
        log_error(f"  FAIL: only {len(tokens)}/5"); return 1

    if args.tokens_out:
        tok_map = {a["email"]: tokens[i] for i, a in enumerate(accounts) if i in tokens}
        Path(args.tokens_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.tokens_out, "w", encoding="utf-8") as f:
            json.dump(tok_map, f, ensure_ascii=False, indent=2)
        log_success(f"  tokens → {args.tokens_out}")

    log_info("\n[Phase 2] S3 上傳")
    cr = s3_creds(tokens[0])
    if not cr: log_error("  FAIL: S3 creds"); return 1
    s3_urls = []
    for i, p in enumerate(POSTS):
        log_info(f"  [{i+1}/5] {p['desc'][:60]}...")
        try:
            s3_urls.append(upload_to_s3(p["image_url"], cr))
            log_success("    OK")
        except Exception as e:
            log_error(f"    FAIL: {e}")
            s3_urls.append(None)

    log_info("\n[Phase 3] 發佈")
    success = 0
    for i in range(5):
        if i not in tokens or s3_urls[i] is None:
            log_info(f"  [{i+1}/5] skip")
            continue
        log_info(f"  [{i+1}/5] {accounts[i]['nickname']}: {POSTS[i]['caption'][:40]}...")
        ok, pid = post_moment(tokens[i], POSTS[i]["caption"], s3_urls[i])
        if ok: log_success(f"    OK -> {pid}"); success += 1
        else: log_error(f"    FAIL: {pid}")
        if i < 4: time.sleep(5)
    log_success(f"\nDone! {success}/5")
    return 0 if success > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
