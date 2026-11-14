// audi 全流程验证: maa1819.com 域名, 真实网络
import { execSync } from 'child_process';

function curlSync(url, opt = {}) {
  const args = ['curl', '-s', '-L', '--max-time', '25'];
  const h = opt.headers || {};
  for (const k of Object.keys(h)) args.push('-H', `'${k}: ${String(h[k]).replace(/'/g, '')}'`);
  if (opt.method) args.push('-X', opt.method);
  args.push(`'${String(url).replace(/'/g, '')}'`);
  try {
    const out = execSync(args.join(' '), { maxBuffer: 1 << 25, encoding: 'buffer' });
    return { content: out.toString('utf8'), headers: {}, statusCode: 200 };
  } catch (e) {
    return { content: '', headers: {}, statusCode: 0 };
  }
}

const cookieJar = {};
globalThis.req = function (url, opt = {}) {
  console.log('  [req]', String(url).slice(0, 110));
  const h = { ...(opt.headers || {}) };
  const ck = Object.entries(cookieJar).map(([k, v]) => k + '=' + v).join('; ');
  if (ck) h['Cookie'] = ck;
  const r = curlSync(url, { ...opt, headers: h });
  // 记录 PHPSESSID (模仿 js 的会话逻辑由 js 自行处理, 这里只透传)
  return r;
};
globalThis.fetch = globalThis.req;

const mod = await import('./audi_open.mjs');
const api = mod.__jsEvalReturn();
await api.init({ skey: 'audi', stype: 0, url: 'https://maa1819.com/zh' });

console.log('== category(chinese) ==');
try {
  const c = await api.category('chinese', '1', false, {});
  const d = JSON.parse(typeof c === 'string' ? c : JSON.stringify(c));
  console.log('条数:', (d.list || []).length, ' pagecount:', d.pagecount);
  (d.list || []).slice(0, 3).forEach(v => console.log('   ', v.vod_id, '|', String(v.vod_name).slice(0, 30), '| pic:', String(v.vod_pic).slice(0, 60)));
  if ((d.list || []).length) {
    const id = d.list[0].vod_id;
    console.log('== detail(', id, ') ==');
    const dt = await api.detail(id);
    const dd = JSON.parse(typeof dt === 'string' ? dt : JSON.stringify(dt));
    const v = dd.list[0];
    console.log('  名称:', v.vod_name.slice(0, 40));
    console.log('  play_from:', v.vod_play_from);
    console.log('  play_url 前100:', v.vod_play_url.slice(0, 100));
  }
} catch (e) {
  console.log('流程异常:', e.message, '\n', (e.stack || '').split('\n').slice(0, 5).join('\n'));
}
