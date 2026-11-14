#!/bin/bash
# 并发扫描 maa 域名段, 找国内可达的 18av 现役镜像
scan_one() {
  d="$1"
  ip=$(getent hosts "$d" 2>/dev/null | awk '{print $1}' | head -1)
  [ -z "$ip" ] && return
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 --resolve "$d:443:$ip" -A 'Mozilla/5.0 Chrome/124.0' "https://$d/zh" 2>/dev/null)
  if [ "$code" = "200" ]; then echo "$d ($ip): HTTP 200 国内可达"; fi
}
export -f scan_one
seq 1800 1 2800 | sed 's/^/maa/' | sed 's/$/.com/' | xargs -P 30 -I{} bash -c 'scan_one {}'
echo "=== 扫描完成 ==="
