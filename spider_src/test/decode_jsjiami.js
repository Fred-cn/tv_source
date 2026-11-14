// 从 jsjiami v7 混淆的 js 里挖出解码后的字符串(找目标域名) v2
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');

// 括号配对截取完整函数体
function cutFn(name) {
  const i = src.indexOf('function ' + name + '(');
  if (i < 0) return null;
  let depth = 0, j = src.indexOf('{', i);
  for (let k = j; k < src.length; k++) {
    const c = src[k];
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return src.slice(i, k + 1); }
  }
  return null;
}

// boot: 从开头到 import 之前 (含轮转 IIFE)
const cut = src.indexOf('import{');
const boot = cut > 0 ? src.slice(0, cut) : '';
const mDec = boot.match(/const\s+(_0x[0-9a-f]+)=(_0x[0-9a-f]+)\s*;/);
if (!mDec) { console.error('未找到解码器引用'); process.exit(1); }
const decoder = mDec[1], fnName = mDec[2];
const fnDec = cutFn(fnName);
if (!fnDec) { console.error('未找到解码器函数体'); process.exit(1); }

// 数组函数: boot 里 IIFE 调用的 _0x1171 —— 从 IIFE 参数里拿名字
const mArr = boot.match(/\((0x[0-9a-f]+),\s*(0x[0-9a-f]+),\s*(_0x[0-9a-f]+),/);
let fnArr = null, arrName = null;
if (mArr) {
  arrName = mArr[3];
  fnArr = cutFn(arrName);
}

// 拼装: 函数声明(提升) + boot
const pieces = [fnDec, fnArr || '', boot];
let sandbox = null;
try {
  sandbox = new Function(pieces.join('\n') + `
    return ${decoder};`)();
} catch (e) {
  console.error('拼装执行失败:', e.message);
  process.exit(1);
}

// 收集调用点并解码
const callRe = new RegExp(decoder + "\\s*\\(\\s*(0x[0-9a-f]+)\\s*,\\s*'((?:[^'\\\\]|\\\\.)*)'\\s*\\)", 'g');
let m;
const seen = new Set();
const out = [];
while ((m = callRe.exec(src)) !== null) {
  try {
    const val = sandbox(parseInt(m[1]), m[2]);
    if (typeof val === 'string' && val.length > 1 && !seen.has(val)) { seen.add(val); out.push(val); }
  } catch (e) { /* ignore */ }
}
console.log('解码字符串总数:', out.length);
const urls = out.filter(s => /https?:\/\/|[a-z0-9-]+\.(com|net|cc|pw|org|xyz|top|vip|moe|app|live|icu|site|fun|pro|fans|bar|info|biz|club|tv|us|me|io|co)\b/i.test(s));
console.log('--- URL/域名类 ---');
urls.forEach(u => console.log('  ', u));
console.log('--- 其余样本(前80) ---');
out.filter(s => !urls.includes(s)).slice(0, 80).forEach(s => console.log('  ', JSON.stringify(s.slice(0, 90))));
