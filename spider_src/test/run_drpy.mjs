// 完整运行 drpy _open js: mock TVBox QuickJS 环境全局, 记录所有请求 URL
import { execSync } from 'child_process';

globalThis.__log = [];

function curlSync(url, opt = {}) {
  const args = ['curl', '-s', '-L', '--max-time', '25'];
  const h = opt.headers || {};
  for (const k of Object.keys(h)) args.push('-H', `'${k}: ${h[k]}'`);
  if (opt.method) args.push('-X', opt.method);
  if (opt.body) args.push('--data-raw', `'${String(opt.body).slice(0, 5000).replace(/'/g, '')}'`);
  args.push(`'${String(url).replace(/'/g, '')}'`);
  try {
    const out = execSync(args.join(' '), { maxBuffer: 1 << 25, encoding: 'buffer' });
    return { content: out.toString('utf8'), headers: {}, statusCode: 200 };
  } catch (e) {
    return { content: e.stdout ? e.stdout.toString('utf8') : '', headers: {}, statusCode: 0 };
  }
}

globalThis.req = function (url, opt) {
  globalThis.__log.push(['req', String(url).slice(0, 200)]);
  return curlSync(url, opt || {});
};
globalThis.fetch = function (url, opt) {
  globalThis.__log.push(['fetch', String(url).slice(0, 200)]);
  const r = curlSync(url, opt || {});
  return Promise.resolve({ text: async () => r.content, json: async () => JSON.parse(r.content || 'null'), status: r.statusCode, headers: new Map() });
};
globalThis.getItem = (k) => null;
globalThis.setItem = () => { };
globalThis.local = (p, f) => f || '';

const mod = await import('./audi_open.js');
const api = mod.__jsEvalReturn();

console.log('== init ==');
let initRet = null;
try {
  initRet = api.init('audi', 0, null);
  console.log('init返回类型:', typeof initRet, initRet ? JSON.stringify(initRet).slice(0, 300) : '');
} catch (e) {
  console.log('init异常:', e.message);
}

console.log('== 实际请求 ==');
globalThis.__log.forEach(([kind, u]) => console.log(`  [${kind}] ${u}`));

console.log('== home ==');
try {
  const homeRet = api.home(true);
  const d = typeof homeRet === 'string' ? JSON.parse(homeRet) : homeRet;
  const cls = d.class || [];
  console.log('home分类数:', cls.length);
  cls.slice(0, 25).forEach(c => console.log('   ', c.type_id, c.type_name));
  console.log('home list数:', (d.list || []).length);
} catch (e) {
  console.log('home异常:', e.message);
}
console.log('== 后续请求 ==');
globalThis.__log.slice(globalThis.__log.length > 6 ? globalThis.__log.length - 6 : 0).forEach(([kind, u]) => console.log(`  [${kind}] ${u}`));
