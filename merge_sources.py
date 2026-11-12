import json
import re
import sys
from urllib.parse import urlparse

# 合并顺序：优先级从高到低（重复时保留靠前文件里的）
INPUT_FILES = ["video.json", "adult.json", "adult-1.json", "adult-2.json"]
OUTPUT_FILE = "video.json"


def load_json(path):
    """读取 JSON，兼容 TVBox 配置里的 // 注释和尾逗号"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    # 去掉整行注释和行尾注释（字符串里没有 // 场景，简单处理即可）
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("//"):
            continue
        lines.append(line)
    text = "\n".join(lines)

    # 去掉尾逗号
    text = re.sub(r",(\s*[}\]])", r"\1", text)

    return json.loads(text)


def dedup_merge(base_list, new_list, key_func):
    """按 key_func 去重合并，返回 (合并列表, 新增数)"""
    seen = {key_func(x) for x in base_list if key_func(x)}
    added = 0
    for item in new_list:
        k = key_func(item)
        if not k or k in seen:
            continue
        seen.add(k)
        base_list.append(item)
        added += 1
    return base_list, added


def site_key(item):
    # key 相同视为同一个源（TVBox 内 key 冲突会异常）
    return str(item.get("key", "")).lower()


def host_of(url):
    return urlparse(str(url).strip()).netloc.lower()


def dedup_sites(sites):
    """
    三级去重（不同名相同 api 也算重复）：
      1. key 相同
      2. http 源 api 完全相同（忽略首尾空白）
      3. http 源同一域名（同站 xml/json 双接口只留一个）
      csp/js 源按 api+ext 区分（同一解析器不同 ext 是不同站点）
    返回 (去重结果, 移除列表)
    """
    seen_key, seen_api, seen_host, seen_csp = set(), set(), set(), set()
    result, removed = [], []
    for s in sites:
        key = str(s.get("key", "")).lower()
        api = str(s.get("api", "")).strip()

        if api.startswith(("http://", "https://")):
            if key in seen_key or api in seen_api or host_of(api) in seen_host:
                removed.append((s.get("key"), s.get("name"), api))
                continue
            seen_key.add(key)
            seen_api.add(api)
            seen_host.add(host_of(api))
            s["api"] = api  # 顺便清掉 api 里的首尾空白
        else:
            rid = (api, s.get("ext"))
            if key in seen_key or rid in seen_csp:
                removed.append((s.get("key"), s.get("name"), api))
                continue
            seen_key.add(key)
            seen_csp.add(rid)
        result.append(s)
    return result, removed


def parse_key(item):
    return item.get("url") or item.get("name")


def generic_key(item):
    return json.dumps(item, sort_keys=True, ensure_ascii=False)


# 更名映射（按旧 key）：显示名和 key 一起改
RENAME_KEYS = {"cat_js_18av": "audi", "cat_js_mt": "cat"}


def clean_text(s):
    """去掉名字里的符号（emoji/括号/竖线/星号/空白等），保留汉字、字母、数字"""
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", str(s))


def clean_names(data):
    """清洗显示名，返回变更列表 [(old_key, old_name, new_key, new_name)]"""
    changed = []
    seen = set()
    for s in data.get("sites", []):
        old_key = str(s.get("key", ""))
        old_name = s.get("name", "")
        if old_key in RENAME_KEYS:
            new_key = new_name = RENAME_KEYS[old_key]
        else:
            new_name = clean_text(old_name) or clean_text(old_key) or old_key
            new_key = old_key  # key 保留原样（*前缀等有隐藏源等约定，不乱动）
        if new_key in seen:  # key 冲突时保持原 key
            new_key = old_key
        seen.add(new_key)
        if new_key != old_key or new_name != old_name:
            changed.append((old_key, old_name, new_key, new_name))
            s["key"], s["name"] = new_key, new_name

    # parses / lives 的显示名同样清洗
    for p in data.get("parses", []):
        if isinstance(p, dict) and p.get("name"):
            n = clean_text(p["name"])
            if n and n != p["name"]:
                p["name"] = n
    for lv in data.get("lives", []):
        if isinstance(lv, dict) and lv.get("name"):
            n = clean_text(lv["name"])
            if n and n != lv["name"]:
                lv["name"] = n
    return changed


def apply_clean():
    """对 video.json / video_ok.json 就地清洗显示名"""
    for path in (OUTPUT_FILE, "video_ok.json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        changed = clean_names(data)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"{path}: 清洗 {len(changed)} 个名称")
        for ok, on, nk, nn in changed:
            print(f"  {ok!r} {on!r} -> key={nk!r} name={nn!r}")


def merge():
    merged = load_json(INPUT_FILES[0])
    stats = []

    for path in INPUT_FILES[1:]:
        data = load_json(path)
        info = {"file": path, "sites": 0, "parses": 0, "flags": 0,
                "rules": 0, "lives": 0, "ads": 0, "ijk": 0}

        # sites 直接汇总，最后统一去重
        sites = merged.setdefault("sites", [])
        before = len(sites)
        sites.extend(data.get("sites", []))
        info["sites"] = len(sites) - before

        # parses 按 url 去重
        parses = merged.setdefault("parses", [])
        before = len(parses)
        dedup_merge(parses, data.get("parses", []), parse_key)
        info["parses"] = len(parses) - before

        # flags / rules / lives / ads / ijk 全量内容去重
        for field in ("flags", "rules", "lives", "ads", "ijk"):
            if field not in data:
                continue
            lst = merged.setdefault(field, [])
            before = len(lst)
            dedup_merge(lst, data.get(field, []), generic_key)
            info[field] = len(lst) - before

        # 单独字段：如果主文件没有就用子文件的
        for field in ("doh", "wallpaper", "spider", "sniffer", "subtitle"):
            if field not in merged and field in data:
                merged[field] = data[field]

        stats.append(info)

    # sites 三级去重
    merged["sites"], removed = dedup_sites(merged.get("sites", []))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=4)

    print(f"合并完成 -> {OUTPUT_FILE}")
    print(f"sites: 原始 {len(merged.get('sites', [])) + len(removed)} "
          f"-> 去重后 {len(merged.get('sites', []))} (移除 {len(removed)})")
    print(f"parses: {len(merged.get('parses', []))}")
    for info in stats:
        print(f"  {info['file']}: +sites={info['sites']} +parses={info['parses']} "
              f"+flags={info['flags']} +rules={info['rules']} +lives={info['lives']} +ads={info['ads']}")
    print("移除的重复源:")
    for k, n, api in removed:
        print(f"  {k} ({n}) {api}")


if __name__ == "__main__":
    merge()
