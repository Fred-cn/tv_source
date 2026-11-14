// 解码 jsjiami v7 全部别名调用点
const fs = require('fs');
const src = fs.readFileSync('audi_open.js', 'utf8');

function cutFn(name) {
  const i = src.indexOf('function ' + name + '(');
  if (i < 0) return null;
  let depth = 0;
  for (let k = src.indexOf('{', i); k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}') { depth--; if (depth === 0) return src.slice(i, k + 1); }
  }
  return null;
}
const decoder = cutFn('_0x13b8');
const arrFn = cutFn('_0x1171');
if (!decoder || !arrFn) { console.error('未找到解码器/数组函数'); process.exit(1); }
// boot: 开头到 import 前, 含轮转 IIFE(打乱数组后索引才正确)
const cut = src.indexOf('import{');
const boot = cut > 0 ? src.slice(0, cut) : '';
const decode = new Function(arrFn + '\n' + decoder + '\n' + boot + '\nreturn _0x13b8;')();

const re = /_0x[0-9a-f]{4,6}\s*\(\s*(0x[0-9a-f]+)\s*,\s*'((?:[^'\\]|\\.)*)'\s*\)/g;
let m;
const seen = new Map();
while ((m = re.exec(src)) !== null) {
  try {
    const v = decode(parseInt(m[1], 16), m[2]);
    if (typeof v === 'string' && !seen.has(m[1] + m[2])) seen.set(m[1] + m[2], v);
  } catch (e) { /* ignore */ }
}
console.log('解码总数:', seen.size);
const urlish = [...seen.entries()].filter(([k, v]) => /[a-z0-9-]+\.[a-z]{2,}|https?:/i.test(v));
console.log('--- 域名/URL ---');
urlish.forEach(([k, v]) => console.log('  ', k, '->', v));
console.log('--- init 默认域名候选 (0x14e / 含av) ---');
[...seen.entries()].filter(([k, v]) => k.startsWith('0x14e') || /av/i.test(v)).forEach(([k, v]) => console.log('  ', k, '->', v));
