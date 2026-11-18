#!/bin/bash
# 构建 Msnii 爬虫 jar:
#   jar/msnii.jar       站点级 jar(含 Init, 供 "jar":"./jar/msnii.jar" 引用)
#   jar/spriederdd.jar  全局 spider jar(基线 dex + Msnii 无 Init 版)
#
# 用法: spider_src/test/merge_spider.sh [基线 spriederdd.jar]
#   基线 jar 需为「未含 Msnii」的原始部署版(默认从 git 历史 71e1846^ 取, 或用 $1 指定)。
#
# 编译用 --release 8: 从源头避开 Java 9+ 的 invokedynamic 字符串拼接 / nestmate 属性,
# 不再依赖 D8 的 desugar 兜底(Android 5.0+ / API 21 安全)。
set -e

REPO=$(cd "$(dirname "$0")/../.." && pwd)
BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT

R8_JAR=${R8_JAR:-$HOME/msnii_csp/r8.jar}
[ -f "$R8_JAR" ] || { echo "缺 r8.jar, 用 R8_JAR=/path/to/r8.jar 指定" >&2; exit 1; }

# 基线 jar: 参数优先, 否则从 git 历史恢复(commit 71e1846 之前 spriederdd.jar 尚未合并 Msnii)
BASE_JAR=$1
if [ -z "$BASE_JAR" ]; then
    BASE_JAR=$BUILD/base_spriederdd.jar
    git -C "$REPO" show 71e1846^:jar/spriederdd.jar > "$BASE_JAR"
    echo "基线 jar: git 71e1846^:jar/spriederdd.jar"
else
    echo "基线 jar: $BASE_JAR"
fi

JAVAC_ARGS="-encoding UTF-8 --release 8 -nowarn"
SRC="$REPO/spider_src"
# test/ 下是调试用 Main(Files/Paths 等 API26+), 不入 jar
SOURCES=$(find "$SRC" -name '*.java' -not -path '*/test/*')

# 1. 编译两个变体: 完整版(含 Init) 与 无 Init 版(仅用于合并)
mkdir -p "$BUILD/full" "$BUILD/noinit"
javac $JAVAC_ARGS -d "$BUILD/full" $SOURCES
javac $JAVAC_ARGS -d "$BUILD/noinit" $(find "$SRC" -name '*.java' -not -path '*/test/*' ! -name 'Init.java')

# 2. D8 生成 dex (只带 spider 类; Spider/Context 为编译桩, 运行时由 app 提供)
mkdir -p "$BUILD/dex_full" "$BUILD/dex_noinit"
D8="java -cp $R8_JAR com.android.tools.r8.D8 --release --min-api 21"
$D8 --output "$BUILD/dex_full" "$BUILD"/full/com/github/catvod/spider/*.class
$D8 --output "$BUILD/dex_noinit" "$BUILD"/noinit/com/github/catvod/spider/*.class

# 3. 合并: 基线 dex + Msnii(无 Init) dex —— 基线已含 Init, 带入会重复定义
mkdir -p "$BUILD/dex_base" "$BUILD/merged"
python3 - "$BASE_JAR" "$BUILD/dex_base" <<'PYEOF'
import sys, zipfile
jar, out = sys.argv[1], sys.argv[2]
d = zipfile.ZipFile(jar).read('classes.dex')
open(out + '/classes.dex', 'wb').write(d)
print('基线 classes.dex:', len(d), 'bytes')
PYEOF
$D8 --output "$BUILD/merged" "$BUILD/dex_base/classes.dex" "$BUILD/dex_noinit/classes.dex"
[ -f "$BUILD/merged/classes2.dex" ] && { echo "意外: 合并后超出单个 dex" >&2; exit 1; }

# 4. 打包 (manifest 不写入 JDK 版本, 避免误判)
python3 - "$REPO" "$BUILD" "$BASE_JAR" <<'PYEOF'
import sys, zipfile, hashlib, os
repo, build, base = sys.argv[1:4]
MANIFEST = b"Manifest-Version: 1.0\r\nDex-Location: classes.dex\r\n\r\n"
targets = [
    ('jar/msnii.jar', build + '/dex_full/classes.dex'),
    ('jar/spriederdd.jar', build + '/merged/classes.dex'),
]
for rel, dex in targets:
    tmp = os.path.join(build, os.path.basename(rel) + '.tmp')
    data = open(dex, 'rb').read()
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        # 固定时间戳 -> 同源码同 dex 产出同 md5, 便于仓库内写死校验值
        for name, blob in (('META-INF/MANIFEST.MF', MANIFEST), ('classes.dex', data)):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, blob)
    dst = os.path.join(repo, rel)
    os.replace(tmp, dst)
    raw = open(dst, 'rb').read()
    print(f'{rel}: {len(raw)}B  md5={hashlib.md5(raw).hexdigest()}')
PYEOF

# 5. 校验: 类齐全 + 新增代码无 API 26+ / invokedynamic 残留
#    基线 jar 里的第三方老代码可能有历史遗留(如 Ljava/util/function/Supplier;),
#    不属于本次构建, 只提示不判失败。
python3 - "$REPO" <<'PYEOF'
import sys, zipfile, logging
logging.disable(logging.CRITICAL)
from androguard.core.dex import DEX

repo = sys.argv[1]
BANNED = ('Ljava/nio/file/', 'Ljava/util/stream/', 'Ljava/time/',
          'Ljava/lang/invoke/', 'Ljava/util/function/')
OURS = {'Lcom/github/catvod/spider/Msnii;', 'Lcom/github/catvod/spider/Msnii$1;',
        'Lcom/github/catvod/spider/Msnii$2;', 'Lcom/github/catvod/spider/Init;'}
ok = True
for rel in ('jar/msnii.jar', 'jar/spriederdd.jar'):
    raw = zipfile.ZipFile(f'{repo}/{rel}').read('classes.dex')
    d = DEX(raw)
    names = {c.get_name() for c in d.get_classes()}
    strs = {s for s in d.get_strings()}
    hits = sorted({x for x in strs if x.startswith(BANNED)})
    print(f'{rel}: dex={raw[:8]!r} api={d.api_version} classes={len(names)}')
    print(f'  含Msnii={"Lcom/github/catvod/spider/Msnii;" in names} '
          f'含Init={"Lcom/github/catvod/spider/Init;" in names}')
    if any('TestMain' in n for n in names):
        print('  !! 误打包 TestMain'); ok = False
    if rel == 'jar/msnii.jar' and hits:
        print('  !! 本次新增代码残留高版本 API:', hits); ok = False
    elif hits:
        print('  提示: 基线第三方代码含', hits, '(非本次构建引入, 原 jar 即有)')
raise SystemExit(0 if ok else 1)
PYEOF

echo "完成。记得同步 video.json / video_ok.json 里的 jar md5。"
