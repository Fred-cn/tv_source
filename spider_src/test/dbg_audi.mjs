// 最小调试: 看 audi_open.js 的 home 原始输出与异常
globalThis.req = function (url, opt) {
  console.log('  [req]', String(url).slice(0, 120));
  return { content: '', headers: {}, statusCode: 0 };
};
globalThis.fetch = function (url, opt) {
  console.log('  [fetch]', String(url).slice(0, 120));
  return Promise.resolve({ text: async () => '', json: async () => null, status: 0, headers: new Map() });
};
const mod = await import('./audi_open.mjs');
console.log('导出键:', Object.keys(mod));
const api = mod.__jsEvalReturn();
console.log('接口:', Object.keys(api));

try {
  const r = await api.init({ skey: 'audi', stype: 0, url: 'https://maa1819.com/zh' });
  console.log('init ok:', JSON.stringify(r));
} catch (e) {
  console.log('init 异常:', e.message, '\n', (e.stack || '').split('\n').slice(0, 4).join('\n'));
}
try {
  const h = await api.home(true);
  console.log('home 类型:', typeof h);
  console.log('home 原文:', String(h).slice(0, 400));
} catch (e) {
  console.log('home 异常:', e.message, '\n', (e.stack || '').split('\n').slice(0, 4).join('\n'));
}
