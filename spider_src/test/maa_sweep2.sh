#!/bin/bash
# 内容验证版扫描: HTTP 200 且页面含 18av 站点特征才算命中
scan_one() {
  d="$1"
  ip=$(getent hosts "$d" 2>/dev/null | awk '{print $1}' | head -1)
  [ -z "$ip" ] && return
  body=$(curl -s --max-time 6 --resolve "$d:443:$ip" -A 'Mozilla/5.0 Chrome/124.0' "https://$d/zh" 2>/dev/null | head -c 30000)
  [ -z "$body" ] && return
  if echo "$body" | grep -qE 'categorylist|div\.posts|chinese_list|uncensored|18av'; then
    echo "$d ($ip): 疑似18av真站"
  fi
}
export -f scan_one
seq 1700 1 2900 | sed 's/^/maa/' | sed 's/$/.com/' | xargs -P 40 -I{} bash -c 'scan_one {}'
echo "=== 内容验证扫描完成 ==="
