// 解码指定 idx/key 对, 或批量列出所有解码串
const fs = require('fs');
const src = fs.readFileSync('audi_open.js', 'utf8');
function cutFn(name) {
  const i = src.indexOf('function ' + name + '(');
  let depth = 0;
  for (let k = src.indexOf('{', i); k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}') { depth--; if (depth === 0) return src.slice(i, k + 1); }
  }
}
const boot = src.slice(0, src.indexOf('import{'));
const decode = new Function(cutFn('_0x1171') + '\n' + cutFn('_0x13b8') + '\n' + boot + '\nreturn _0x13b8;')();

if (process.argv.length >= 4) {
  console.log(decode(parseInt(process.argv[2], 16), process.argv[3]));
} else {
  const re = /_0x[0-9a-f]{4,6}\s*\(\s*(0x[0-9a-f]+)\s*,\s*'((?:[^'\\]|\\.)*)'\s*\)/g;
  let m;
  const seen = new Map();
  while ((m = re.exec(src)) !== null) {
    try {
      const v = decode(parseInt(m[1], 16), m[2]);
      if (typeof v === 'string' && !seen.has(v)) seen.set(v, m[1] + m[2]);
    } catch (e) { }
  }
  // 只打印像键名的短串
  [...seen.keys()].filter(v => v.length <= 20).forEach(v => console.log(JSON.stringify(v)));
}
