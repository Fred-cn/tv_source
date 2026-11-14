#!/bin/bash
# 把 Msnii 类(不含Init)合并进 spriederdd.jar 的 dex, 产出新的全局 spider jar
set -e
cd /home/dev/msnii_csp

# 1. 编译两个变体: 完整版(含Init, 站点级jar用) 和 无Init版(合并用)
rm -rf classes_full classes_noInit merged_out dex_spried dex_msnii
mkdir -p classes_full classes_noInit merged_out dex_spried dex_msnii
javac -encoding UTF-8 -d classes_full $(find spider_src -name '*.java')
javac -encoding UTF-8 -d classes_noInit $(find spider_src -name '*.java' ! -name 'Init.java')

# 2. 提取两个 jar 的 dex
python3 - <<'PYEOF'
import zipfile
z = zipfile.ZipFile('spriederdd_deploy.jar')
z.extract('classes.dex', 'dex_spried')
print('spriederdd classes.dex:', len(z.read('classes.dex')), 'bytes')
z2 = zipfile.ZipFile('msnii.jar')
z2.extract('classes.dex', 'dex_msnii')
print('msnii classes.dex:', len(z2.read('classes.dex')), 'bytes')
PYEOF

# 3. D8 合并 (dex 输入)
java -cp r8.jar com.android.tools.r8.D8 --release --min-api 21 --output merged_out dex_spried/classes.dex dex_msnii/classes.dex && echo "D8合并成功"
ls -la merged_out/

# 4. 校验合并结果: androguard 统计类
python3 - <<'PYEOF'
import logging
logging.disable(logging.DEBUG)
from androguard.core.dex import DEX
d = DEX(open('merged_out/classes.dex', 'rb').read())
names = [c.get_name() for c in d.get_classes()]
print('合并后类数:', len(names))
print('含Msnii:', any('Msnii' in n for n in names))
print('Init存在:', 'Lcom/github/catvod/spider/Init;' in names)
msnii = [c for c in d.get_classes() if c.get_name() == 'Lcom/github/catvod/spider/Msnii;']
if msnii:
    print('Msnii 父类:', msnii[0].get_superclassname())
    print('Msnii 方法数:', len(msnii[0].get_methods()))
PYEOF

# 5. 打包新 spriederdd.jar (沿用原 manifest 结构)
python3 - <<'PYEOF'
import zipfile, hashlib
old = zipfile.ZipFile('spriederdd_deploy.jar')
new = zipfile.ZipFile('spriederdd_new.jar', 'w')
for item in old.namelist():
    if item == 'classes.dex':
        new.write('merged_out/classes.dex', item)
    else:
        new.writestr(item, old.read(item))
new.close()
h = hashlib.md5(open('spriederdd_new.jar', 'rb').read()).hexdigest()
print('spriederdd_new.jar md5:', h, 'size:', len(open('spriederdd_new.jar','rb').read()))
PYEOF
