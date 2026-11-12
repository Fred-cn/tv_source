import json
import sys
import time
import xml.etree.ElementTree as ET
import concurrent.futures as cf
from datetime import datetime

import requests

CONFIG_FILE = "video.json"      # 全量去重结果（不论可用性，会回写修正后的 type）
OK_FILE = "video_ok.json"       # 严格验证通过的可用源
REPORT_FILE = "site_check_report.txt"

TIMEOUT = 10
RETRY = 1
WORKERS = 32

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
}

session = requests.Session()
session.headers.update(HEADERS)


def join_url(url, **params):
    sep = "&" if "?" in url else "?"
    return url + sep + "&".join(f"{k}={v}" for k, v in params.items())


def sniff_format(text):
    """根据响应开头判断实际是 xml 还是 json"""
    s = (text or "").lstrip()[:120].lower()
    if s.startswith(("<?xml", "<rss", "<list")) or (s.startswith("<") and "<" in s[1:]):
        return "xml"
    if s.startswith("{") or s.startswith("["):
        return "json"
    return None


def validate_xml(content):
    """严格验证 MacCMS XML: rss -> video(name/dd播放地址)
    返回 (ok, detail, first_id, has_play)"""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        return False, f"XML解析失败({str(e)[:40]})", None, False
    except Exception:
        return False, "XML解码失败", None, False

    videos = list(root.iter("video"))
    if not videos:
        return False, "XML无video节点", None, False

    v = videos[0]
    name = (v.findtext("name") or "").strip()
    if not name:
        return False, "video节点缺name", None, False

    vid = (v.findtext("id") or "").strip() or None
    play = ""
    for dd in v.iter("dd"):
        if dd.text and dd.text.strip():
            play = dd.text.strip()
            break
    has_play = bool(play) and "http" in play
    if play and not has_play:
        return False, "播放地址非URL", len(videos), False
    return True, f"XML正常({len(videos)}部/页)", vid, has_play


def validate_json(data):
    """严格验证 MacCMS JSON: code=1 + list(vod_id/vod_name[/vod_play_url])
    返回 (ok, detail, first_id, has_play)"""
    if not isinstance(data, dict):
        return False, "JSON不是对象", None, False
    lst = data.get("list") or []
    if not lst:
        code = data.get("code")
        return False, f"JSON列表为空(code={code})", None, False
    it = lst[0]
    if it.get("vod_id") is None or not it.get("vod_name"):
        return False, "缺少vod_id/vod_name字段", None, False
    play = it.get("vod_play_url") or ""
    has_play = "http" in play
    return True, f"JSON正常({len(lst)}部/页)", str(it.get("vod_id")), has_play


def check_play_detail(api, stype, vid):
    """列表里没带播放地址时，抽查详情接口"""
    if not vid:
        return False, "无法获取id查详情"
    for u in (join_url(api, ac="videolist", ids=vid), join_url(api, ac="detail", ids=vid)):
        try:
            r = session.get(u, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            if stype == "xml":
                try:
                    root = ET.fromstring(r.content)
                except Exception:
                    continue
                for v in root.iter("video"):
                    if (v.findtext("id") or "").strip() == str(vid):
                        for dd in v.iter("dd"):
                            if dd.text and "http" in dd.text:
                                return True, "详情含播放地址"
            else:
                try:
                    d = json.loads(r.text)
                except Exception:
                    continue
                lst = d.get("list") if isinstance(d, dict) else d
                if lst:
                    if "http" in (lst[0].get("vod_play_url") or ""):
                        return True, "详情含播放地址"
        except Exception:
            continue
    return False, "详情接口无播放数据"


def gen_variants(api):
    """生成同一 provider 的接口变体: xml<->json 风味、http<->https、at参数、尾斜杠"""
    a = api.strip()
    low = a.lower()
    out = []

    def add(u):
        u = u.strip()
        if u and u != a and u not in out:
            out.append(u)

    # 1. 风味路径互换
    for old, new in [("/at/xml", "/at/json"), ("/at/json", "/at/xml"),
                     ("xml.php", "json.php"), ("json.php", "xml.php"),
                     ("apixml", "apijson"), ("apijson", "apixml"),
                     ("/vod/xml", "/vod/json"), ("/vod/json", "/vod/xml"),
                     ("/xml/", "/json/"), ("/json/", "/xml/")]:
        if old in low:
            idx = low.find(old)
            add(a[:idx] + new + a[idx + len(old):])

    # 2. at= 参数（maccms/seacms 通用）
    sep = "&" if "?" in a else "?"
    add(f"{a}{sep}at=json")
    add(f"{a}{sep}at=xml")

    # 3. http<->https
    if low.startswith("https://"):
        add("http://" + a[8:])
    elif low.startswith("http://"):
        add("https://" + a[7:])

    # 4. 尾斜杠
    add(a.rstrip("/") if a.endswith("/") else a + "/")
    return out[:10]


def repair_site(site):
    """对失效源探测接口变体，找到可严格解析的格式
    返回 (new_api, new_type, detail) 或 None"""
    api = str(site.get("api", "")).strip()
    for v in gen_variants(api):
        r = check_site({"key": site.get("key", "?"), "name": site.get("name", "?"),
                        "type": None, "api": v})
        if r["status"] == "OK":
            return v, r.get("fixed_type"), r["detail"]
        time.sleep(0.3)
    return None


def check_site(site):
    """检测单个源，返回 dict(status, detail, fixed_type)"""
    key = site.get("key", "?")
    name = site.get("name", "?")
    api = str(site.get("api", "")).strip()
    stype = site.get("type")

    if not api.startswith(("http://", "https://")):
        return {"key": key, "name": name, "api": api, "type": stype,
                "status": "SKIP", "detail": "csp/js本地解析", "fixed_type": None}

    candidates = [api]
    if stype == 0:
        # TVBox type=0 实际请求 ac=videolist, 优先; 纯地址兜底
        candidates = [join_url(api, ac="videolist"), api]
    elif stype == 1:
        candidates = [join_url(api, ac="videolist"), join_url(api, ac="list"), api]

    last_err = ""
    for u in candidates:
        for attempt in range(RETRY + 1):
            if attempt:
                time.sleep(0.5)
            try:
                r = session.get(u, timeout=TIMEOUT)
            except requests.exceptions.Timeout:
                last_err = "超时"
                continue
            except requests.exceptions.SSLError:
                last_err = "SSL错误"
                break
            except requests.exceptions.ConnectionError:
                last_err = "连接失败"
                break
            except Exception as e:
                last_err = f"异常:{str(e)[:40]}"
                continue

            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}"
                continue

            body = r.text or ""
            if not body.strip():
                last_err = "空响应"
                continue

            fmt = sniff_format(body)
            if fmt is None:
                last_err = f"无法识别格式({body.strip()[:30]!r})"
                continue

            # api格式变了: 实际返回格式与声明的 type 不一致时自动修正
            actual_type = 0 if fmt == "xml" else 1
            fixed_type = actual_type if actual_type != stype else None

            if fmt == "xml":
                ok, detail, vid, has_play = validate_xml(r.content)
            else:
                try:
                    data = json.loads(body)
                except Exception:
                    last_err = "JSON解析失败"
                    continue
                ok, detail, vid, has_play = validate_json(data)

            if not ok:
                last_err = detail
                continue

            # 列表可用；没带播放地址的再抽查详情
            if not has_play:
                p_ok, p_detail = check_play_detail(api, actual_type, vid)
                if not p_ok:
                    last_err = f"列表可解析但{p_detail}"
                    break  # 换下一个候选
                detail += f", {p_detail}"

            note = f" [type {stype}->{actual_type}]" if fixed_type is not None else ""
            return {"key": key, "name": name, "api": api, "type": stype,
                    "status": "OK", "detail": detail + note, "fixed_type": fixed_type}

    return {"key": key, "name": name, "api": api, "type": stype,
            "status": "DEAD", "detail": last_err, "fixed_type": None}


def main():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    sites = data.get("sites", [])
    print(f"共 {len(sites)} 个源，严格验证（TVBox解析标准, 超时{TIMEOUT}s, 并发{WORKERS}）...")

    results = []
    done = 0
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(check_site, sites):
            results.append(r)
            done += 1
            if done % 20 == 0:
                print(f"  进度 {done}/{len(sites)}")

        # 二次复测失效源，减少瞬时超时/限流误判
        dead_idx = [i for i, r in enumerate(results) if r["status"] == "DEAD"]
        if dead_idx:
            print(f"  对 {len(dead_idx)} 个失效源二次复测...")
            for i, r in zip(dead_idx, ex.map(check_site, [sites[i] for i in dead_idx])):
                if r["status"] == "OK":
                    print(f"    复测通过: {r['key']}")
                    results[i] = r

        # 三次修复: 对仍失效的源探测接口变体(xml<->json、http<->https、at参数)
        repairs = []
        repairable = [(i, r) for i, r in enumerate(results)
                      if r["status"] == "DEAD" and r["api"].startswith(("http://", "https://"))]
        if repairable:
            print(f"  对 {len(repairable)} 个失效源尝试格式修复...")
            for (i, old_r), res in zip(repairable, ex.map(lambda x: repair_site(sites[x[0]]), repairable)):
                if res:
                    new_api, new_type, detail = res
                    sites[i]["api"] = new_api
                    if new_type is not None:
                        sites[i]["type"] = new_type
                    results[i] = {**old_r, "api": new_api, "type": new_type, "status": "OK",
                                  "detail": f"已修复: {detail}",
                                  "fixed_type": new_type if new_type != old_r["type"] else None}
                    repairs.append((old_r["key"], old_r["api"], new_api, new_type, detail))
                    print(f"    修复成功: {old_r['key']}  {old_r['api']} -> {new_api}")

    # 回写 type 修正到全量 video.json（不按可用性删源）
    fixes = [(r["key"], r["type"], r["fixed_type"]) for r in results if r["fixed_type"] is not None]
    for s, r in zip(sites, results):
        if r["fixed_type"] is not None:
            s["type"] = r["fixed_type"]
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    # 可用版
    ok_data = dict(data)
    ok_data["sites"] = [s for s, r in zip(sites, results) if r["status"] in ("OK", "SKIP")]
    with open(OK_FILE, "w", encoding="utf-8") as f:
        json.dump(ok_data, f, ensure_ascii=False, indent=4)

    n_ok = sum(1 for r in results if r["status"] == "OK")
    n_dead = sum(1 for r in results if r["status"] == "DEAD")
    n_skip = sum(1 for r in results if r["status"] == "SKIP")

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(f"检测时间: {datetime.now():%Y-%m-%d %H:%M:%S}  (严格模式: TVBox解析验证+播放数据+格式修复)\n")
        f.write(f"总计: {len(results)}  可用: {n_ok} (其中修复 {len(repairs)})  失效: {n_dead}  "
                f"跳过(本地jar): {n_skip}  type修正: {len(fixes)}\n")
        f.write("=" * 90 + "\n\n[格式修复成功] 同一provider换接口风格后恢复, 已回写api/type到video.json\n")
        for k, old_api, new_api, new_type, detail in repairs:
            f.write(f"  {k}\n    旧: {old_api}\n    新: {new_api}  (type={new_type})  [{detail}]\n")
        f.write("\n[type修正] api实际格式与声明type不符, 已自动修正并回写video.json\n")
        for k, old, new in fixes:
            f.write(f"  {k}  type {old} -> {new}\n")
        f.write("\n[失效源]\n")
        for r in results:
            if r["status"] == "DEAD":
                f.write(f"  {r['key']}  ({r['name']})  type={r['type']}  {r['api']}  -> {r['detail']}\n")
        f.write("\n[跳过(csp/js 本地解析, 未测)]\n")
        for r in results:
            if r["status"] == "SKIP":
                f.write(f"  {r['key']}  ({r['name']})  type={r['type']}  {r['api']}\n")
        f.write("\n[可用源]\n")
        for r in results:
            if r["status"] == "OK":
                f.write(f"  {r['key']}  ({r['name']})  type={r['type']}  {r['api']}  -> {r['detail']}\n")

    print(f"\n检测完成: 可用 {n_ok} / 失效 {n_dead} / 跳过 {n_skip} / type修正 {len(fixes)}")
    print(f"全量(含失效,已修正type): {CONFIG_FILE}  可用版: {OK_FILE}  报告: {REPORT_FILE}")


if __name__ == "__main__":
    main()
