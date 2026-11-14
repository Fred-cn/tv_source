import json
import re
import sys
import zipfile
import concurrent.futures as cf
from datetime import datetime

import requests

CONFIG_FILE = "video.json"
OK_FILE = "video_ok.json"
REPORT_FILE = "site_check_report.txt"

# 各 jar 对 csp 类的支持（站点级 jar 可覆盖全局 spider）
JARS = {
    "jar/spriederdd.jar": None,   # md5 运行时计算
    "jar/fm_push.jar": None,
    "jar/XBiubiu.jar": None,
    "jar/spider.jar": None,
    "jar/msnii.jar": None,        # csp_Msnii (msnii系分类包装)
}


def md5_of(path):
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def jar_classes(path):
    """从 dex 里提取 com.github.catvod.spider.* 类名(去内部类)"""
    z = zipfile.ZipFile(path)
    data = b"".join(z.read(n) for n in z.namelist() if n.endswith(".dex"))
    return {m.decode() for m in re.findall(rb"Lcom/github/catvod/spider/([A-Za-z0-9_]+);", data)}


def test_ext(url):
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 Chrome/124.0"})
        body = (r.text or "").strip()
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        if not body:
            return False, "空文件"
        if body.lstrip().lower().startswith(("<!doctype", "<html")):
            return False, "返回HTML页"
        if len(body) < 100 and ("not_login" in body or "msg" in body):
            return False, f"异常响应({body[:50]})"
        return True, f"{len(body)}B"
    except requests.exceptions.Timeout:
        return False, "超时"
    except requests.exceptions.SSLError:
        return False, "SSL错误"
    except Exception as e:
        return False, type(e).__name__


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # ---- jar 能力 ----
    jar_support = {}
    for path in JARS:
        jar_support[path] = jar_classes(path)
    support_all = set().union(*jar_support.values())

    # 配置实际需要的类
    csp = [s for s in data["sites"] if not str(s.get("api", "")).startswith(("http://", "https://"))]
    need = {str(s["api"])[4:] for s in csp if str(s.get("api", "")).startswith("csp_")}

    print("jar 爬虫类覆盖:")
    for p, cs in jar_support.items():
        print(f"  {p}: {len(cs)} 类, 命中所需 {len(cs & need)}/{len(need)}")

    # ---- 分类 csp/js 源 ----
    print(f"csp/js 源共 {len(csp)} 个，开始分类...")

    # 远程 ext 并发测试（csp_Msnii 类多行 ext: 首行才是 URL）
    def ext_url(v):
        return v.split("\n")[0].strip()

    ext_items = {s["key"]: ext_url(s["ext"]) for s in csp
                 if isinstance(s.get("ext"), str) and ext_url(s["ext"]).startswith("http")}
    ext_status = {}
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        for k, (ok, detail) in zip(ext_items, ex.map(test_ext, ext_items.values())):
            ext_status[k] = (ok, detail)

    rows = []   # (site, verdict, reason)
    for s in csp:
        key = s.get("key", "?")
        api = str(s.get("api", ""))
        ext = s.get("ext")

        # 本地相对路径 js: 仓库里不存在 -> 坏
        if api.startswith("./") or (isinstance(ext, str) and ext.startswith("./")):
            import os
            local = api if api.startswith("./") else ext
            if os.path.exists(local.lstrip("./")):
                rows.append((s, "OK", "本地文件存在"))
            else:
                rows.append((s, "DEAD", f"本地文件缺失: {local}"))
            continue

        cls = api[4:] if api.startswith("csp_") else None
        if cls and cls not in support_all:
            rows.append((s, "DEAD", f"爬虫类 {cls} 在仓库{len(jar_support)}个jar中均不存在"))
            continue

        # 类存在；确定用哪个 jar（站点级 jar 覆盖）
        site_jar = None
        for p, cs in jar_support.items():
            if cls and cls in cs and (site_jar is None or p != "jar/spriederdd.jar"):
                site_jar = p

        if isinstance(ext, str) and ext.startswith("http"):
            ok, detail = ext_status.get(key, (False, "未测"))
            if not ok:
                rows.append((s, "DEAD", f"ext失效({detail})"))
                continue
            rows.append((s, "OK", f"类{cls}于{site_jar}, ext可达({detail})"))
        else:
            rows.append((s, "OK", f"类{cls}于{site_jar}, 无ext(纯jar类)"))

    # ---- 修复动作 ----
    # 1. spider 指向"覆盖所需类最多"的仓库内 jar（原 dd.ma 短链已死）
    best = max(jar_support, key=lambda p: len(jar_support[p] & need))
    old_spider = data.get("spider")
    new_spider = f"./{best};md5;{md5_of(best)}"
    data["spider"] = new_spider
    print(f"spider: {old_spider} -> {new_spider}")

    # 2. 类不在主 jar 但在其他 jar 有的源，加站点级 jar（带 md5 校验）
    per_jar = 0
    for s, verdict, reason in rows:
        cls = str(s.get("api", ""))[4:] if str(s.get("api", "")).startswith("csp_") else None
        if not cls or cls in jar_support[best]:
            continue
        for p, cs in jar_support.items():
            if cls in cs:
                s["jar"] = f"./{p};md5;{md5_of(p)}"
                per_jar += 1
                print(f"  站点级jar: {s.get('name')} ({cls}) -> {p}")
                break

    # ---- 回写 ----
    # ok 版 HTTP 源沿用上一轮检测结果（video_ok.json 里现有的），csp 源按本轮判定
    prev_ok = json.load(open(OK_FILE, encoding="utf-8"))
    ok_http = {(s.get("key"), s.get("api")) for s in prev_ok.get("sites", [])
               if str(s.get("api", "")).startswith(("http://", "https://"))}
    csp_ok_ids = {id(s) for s, v, _ in rows if v == "OK"}
    ok_data = dict(data)
    ok_data["sites"] = [s for s in data["sites"]
                        if ((str(s.get("api", "")).startswith(("http://", "https://"))
                             and (s.get("key"), s.get("api")) in ok_http)
                            or id(s) in csp_ok_ids)]

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    with open(OK_FILE, "w", encoding="utf-8") as f:
        json.dump(ok_data, f, ensure_ascii=False, indent=4)

    n_ok = sum(1 for _, v, _ in rows if v == "OK")
    with open(REPORT_FILE, "a", encoding="utf-8") as f:
        f.write("\n\n" + "=" * 90 + "\n")
        f.write(f"[csp/js 检测] {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"全局jar: {best}  各jar覆盖: "
                + ", ".join(f"{p}={len(jar_support[p])}类/命中{len(jar_support[p] & need)}" for p in jar_support)
                + f"  站点级jar {per_jar} 处\n")
        f.write(f"csp/js 源 {len(rows)} 个: 可用 {n_ok} / 必死 {len(rows)-n_ok}  (ext可达≠目标站可爬, 最终以TVBox实测为准)\n\n")
        f.write("-- 必死 --\n")
        for s, v, reason in rows:
            if v == "DEAD":
                f.write(f"  {s.get('key')}  ({s.get('name')})  {s.get('api')}  ext={s.get('ext')}  -> {reason}\n")
        f.write("\n-- 可用(待TVBox实测) --\n")
        for s, v, reason in rows:
            if v == "OK":
                f.write(f"  {s.get('key')}  ({s.get('name')})  {s.get('api')}  -> {reason}\n")

    print(f"\ncsp/js: 可用 {n_ok} / 必死 {len(rows)-n_ok}")
    print(f"video.json(全量+spider修复) / {OK_FILE}(可用) / {REPORT_FILE}(已追加csp章节)")


if __name__ == "__main__":
    main()
