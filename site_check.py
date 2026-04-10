import json
import requests
import sys

TIMEOUT = 5


def build_line_map(file_path):
    """
    建立 api -> 行号 的映射（取第一次出现）
    """
    line_map = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if '"api"' in line:
                # 简单提取 api 值
                try:
                    key = line.split('"api"')[1].split('"')[1]
                    if key not in line_map:
                        line_map[key] = idx
                except:
                    pass
    return line_map


def check_url(url):
    """
    检测 URL 是否可用
    """
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return True, r.status_code
        return False, r.status_code
    except Exception as e:
        return False, str(e)


def main(file_path):
    # 读取 JSON
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sites = data.get("sites", [])
    line_map = build_line_map(file_path)

    print(f"{'KEY':30} {'STATUS':10} {'LINE':6} API")

    print("-" * 80)

    for item in sites:
        api = item.get("api", "")
        key = item.get("key", "")

        # 只检测 http/https
        if not (api.startswith("http://") or api.startswith("https://")):
            continue

        ok, info = check_url(api)

        status = "VALID" if ok else "INVALID"
        line = line_map.get(api, -1)

        print(f"{key:30} {status:10} {str(line):6} {api}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check.py config.json")
        sys.exit(1)

    main(sys.argv[1])