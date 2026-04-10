import re

INPUT_FILE = "tvbox_live.txt"
OUTPUT_OK = "format_ok.txt"
OUTPUT_ERR = "format_error.txt"

# 支持协议
VALID_SCHEMES = ("http://", "https://", "rtmp://", "mitv://", "vjms://")

# URL基础正则（宽松版）
URL_REGEX = re.compile(
    r'^(http|https|rtmp|mitv|vjms)://[^\s]+$'
)


def is_valid_url(url):
    # 协议检查
    if not url.startswith(VALID_SCHEMES):
        return False, "协议错误"

    # 基本结构检查
    if not URL_REGEX.match(url):
        return False, "URL格式错误"

    return True, ""


def main():
    current_group = None

    ok_lines = []
    err_lines = []

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            raw = line.rstrip("\n")
            line = line.strip()

            if not line:
                continue

            # 分组检测
            if line.endswith(",#genre#"):
                group = line[:-8].strip()
                if not group:
                    err_lines.append((lineno, raw, "分组名为空"))
                else:
                    current_group = group
                    ok_lines.append(raw)
                continue

            # 非分组但没有分组上下文
            if not current_group:
                err_lines.append((lineno, raw, "未定义分组"))
                continue

            # 必须包含一个逗号
            if "," not in line:
                err_lines.append((lineno, raw, "缺少逗号"))
                continue

            parts = line.split(",")

            # 多逗号情况
            if len(parts) < 2:
                err_lines.append((lineno, raw, "格式错误"))
                continue

            name = parts[0].strip()
            url = parts[-1].strip()

            if not name:
                err_lines.append((lineno, raw, "频道名为空"))
                continue

            if not url:
                err_lines.append((lineno, raw, "URL为空"))
                continue

            valid, reason = is_valid_url(url)
            if not valid:
                err_lines.append((lineno, raw, reason))
                continue

            ok_lines.append(raw)

    # 写结果
    with open(OUTPUT_OK, "w", encoding="utf-8") as f:
        for line in ok_lines:
            f.write(line + "\n")

    with open(OUTPUT_ERR, "w", encoding="utf-8") as f:
        for lineno, line, reason in err_lines:
            f.write(f"[第{lineno}行] {reason} -> {line}\n")

    print("检测完成：")
    print(f"正常: {len(ok_lines)}")
    print(f"异常: {len(err_lines)}")


if __name__ == "__main__":
    main()