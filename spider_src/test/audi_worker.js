// audi (18av) Cloudflare Worker 反代
// 部署到用户的 CF zone (live-box.cfd) 后, 路由 tvbox.live-box.cfd/audi/* ->
// https://maa1829.com/*, HTML 里的站内绝对链接同步改写, 供国内 TVBox 直连。
// 配置侧: audi 源的 ext 填 "https://tvbox.live-box.cfd/audi/zh"

const UPSTREAM = 'https://maa1829.com';
const PREFIX = '/audi';
const UP_HOST = 'maa1829.com';
const MY_HOST = 'tvbox.live-box.cfd';

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.hostname !== MY_HOST || !url.pathname.startsWith(PREFIX)) {
      return new Response('audi proxy: not found', { status: 404 });
    }
    const path = url.pathname.slice(PREFIX.length) || '/zh';
    const target = UPSTREAM + path + url.search;

    const headers = new Headers(request.headers);
    headers.delete('host');
    headers.delete('cf-connecting-ip');
    headers.delete('cf-ipcountry');
    headers.delete('cf-ray');
    headers.delete('cf-visitor');
    headers.delete('x-forwarded-proto');
    headers.set('referer', UPSTREAM + '/zh');

    let resp;
    try {
      resp = await fetch(target, {
        method: request.method,
        headers,
        body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
        redirect: 'manual',
      });
    } catch (e) {
      return new Response('upstream error: ' + e.message, { status: 502 });
    }

    // 30x: 把上游 Location 改写回本域代理路径
    if (resp.status >= 300 && resp.status < 400) {
      const loc = resp.headers.get('location');
      if (loc) {
        const abs = new URL(loc, UPSTREAM);
        const out = new Response(null, { status: resp.status, headers: { location: PREFIX + abs.pathname + abs.search } });
        for (const [k, v] of resp.headers) {
          if (k.toLowerCase() === 'set-cookie') out.headers.append('set-cookie', v);
        }
        return out;
      }
    }

    const ct = resp.headers.get('content-type') || '';
    // HTML: 改写站内绝对 URL 为代理路径(图片/播放链接都能走通)
    if (ct.includes('text/html')) {
      let html = await resp.text();
      html = html.split(`https://${UP_HOST}`).join(PREFIX)
        .split(`http://${UP_HOST}`).join(PREFIX)
        .split(`"${UP_HOST}`).join(`"${MY_HOST}`);
      const out = new Response(html, { status: resp.status, headers: { 'content-type': 'text/html; charset=utf-8' } });
      return out;
    }

    const out = new Response(resp.body, resp);
    out.headers.delete('content-security-policy');
    out.headers.delete('x-frame-options');
    return out;
  },
};
