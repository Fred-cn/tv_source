import requests
import urllib3
import base64
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

INPUT_FILE = "live.txt"
OUT_VALID = "live_valid.txt"
OUT_INVALID = "live_invalid.txt"

TIMEOUT = (3, 5)
MAX_WORKERS = 20
RETRIES = 2

urllib3.disable_warnings()
session = requests.Session()


# =========================
# 1. 检查 ffmpeg/ffprobe
# =========================
def check_ffmpeg():
    try:
        subprocess.run(
            ["ffprobe", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3
        )
        return True
    except Exception:
        return False


# =========================
# 2. 协议解析
# =========================
def resolve_url(url, depth=3):
    for _ in range(depth):
        if not url:
            return None

        if url.startswith("mitv://"):
            url = url.replace("mitv://", "")
            continue

        if url.startswith("vjms://"):
            try:
                encoded = url.replace("vjms://", "")
                url = base64.b64decode(encoded).decode("utf-8", errors="ignore")
                continue
            except:
                return None

        break

    return url


# =========================
# 3. 解析文件
# =========================
def parse_file(file):
    group = None
    items = []

    with open(file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            if line.endswith(",#genre#"):
                group = line[:-8]
                continue

            if "," in line and group:
                name, url = line.split(",", 1)
                items.append((group, name.strip(), url.strip()))

    return items


# =========================
# 4. HTTP请求
# =========================
def fetch(url):
    try:
        return session.get(
            url,
            timeout=TIMEOUT,
            verify=False,
            headers={"User-Agent": "Mozilla/5.0"},
        )
    except:
        return None


# =========================
# 5. m3u8检测
# =========================
def check_m3u8(resp):
    try:
        text = resp.text[:800]
        if "#EXTM3U" not in text:
            return False
        if "EXTINF" not in text and "EXT-X-STREAM-INF" not in text:
            return False
        if "<html" in text.lower():
            return False
        return True
    except:
        return False


# =========================
# 6. RTSP / RTMP 检测
# =========================
def check_stream(url, is_rtsp=False):
    cmd = ["ffprobe"]

    if is_rtsp:
        cmd += ["-rtsp_transport", "tcp"]

    cmd += [
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1",
        url
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


# =========================
# 7. 核心检测
# =========================
def check(item):
    group, name, url = item

    # RTMP / RTSP
    if url.startswith("rtmp://"):
        return (group, name, url, check_stream(url, False))

    if url.startswith("rtsp://"):
        return (group, name, url, check_stream(url, True))

    url = resolve_url(url)
    if not url:
        return (group, name, url, False)

    for _ in range(RETRIES):
        resp = fetch(url)

        if not resp:
            if url.startswith("http://"):
                resp = fetch(url.replace("http://", "https://"))
            elif url.startswith("https://"):
                resp = fetch(url.replace("https://", "http://"))

        if not resp or resp.status_code != 200:
            continue

        if ".m3u8" in url:
            if not check_m3u8(resp):
                continue

        return (group, name, url, True)

    return (group, name, url, False)


# =========================
# 8. 写文件
# =========================
def write_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        cur = None
        for g, n, u in data:
            if g != cur:
                cur = g
                f.write(f"{g},#genre#\n")
            f.write(f"{n},{u}\n")


# =========================
# 9. 主函数
# =========================
def main():

    # 🔥 ffmpeg检测（你要求的重点）
    if not check_ffmpeg():
        print("❌ 未检测到 ffprobe/ffmpeg，请先安装 FFmpeg 并加入 PATH")
        print("   下载: https://ffmpeg.org/")
        sys.exit(1)

    items = parse_file(INPUT_FILE)

    # 去重
    seen = set()
    unique = []
    for i in items:
        if i[2] not in seen:
            seen.add(i[2])
            unique.append(i)

    valid = []
    invalid = []

    with ThreadPoolExecutor(MAX_WORKERS) as ex:
        futures = [ex.submit(check, i) for i in unique]

        for f in tqdm(as_completed(futures), total=len(futures), desc="检测中"):
            g, n, u, ok = f.result()

            if ok:
                valid.append((g, n, u))
            else:
                invalid.append((g, n, u))

    valid.sort()
    invalid.sort()

    write_file(OUT_VALID, valid)
    write_file(OUT_INVALID, invalid)

    print("\n完成：")
    print("有效:", len(valid))
    print("无效:", len(invalid))


if __name__ == "__main__":
    main()