package com.github.catvod.spider;

import android.content.Context;

import com.github.catvod.crawler.Spider;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.security.SecureRandom;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import javax.net.ssl.HostnameVerifier;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

/**
 * msnii 系(美少女/淫水机/香奶儿/白嫖/黄AV) MacCMS XML 源的 csp 包装。
 *
 * 这些站的 API 功能完整(列表/详情/播放/搜索)，但分类节点 <class> 全空，
 * type=0 直连时 app 主页一片空白。本类通过 ext 手工提供分类映射:
 *
 *   ext 第一行 = xml 接口地址
 *   其余每行 = tid=分类名
 *
 * 例:
 *   https://www.msnii.com/api/xml.php
 *   35=日系番号
 *   26=日系有码
 */
public class Msnii extends Spider {

    private static final String UA = "okhttp/3.12.0";
    private static final int CONNECT_TIMEOUT = 10000;
    private static final int READ_TIMEOUT = 20000;

    private String apiUrl = "";
    private final LinkedHashMap<String, String> cates = new LinkedHashMap<>();

    @Override
    public void init(Context context, String extend) {
        try {
            if (extend == null || extend.trim().isEmpty()) return;
            String[] lines = extend.split("\n");
            apiUrl = lines[0].trim();
            for (int i = 1; i < lines.length; i++) {
                String line = lines[i].trim();
                if (line.isEmpty()) continue;
                int eq = line.indexOf('=');
                if (eq <= 0) continue;
                cates.put(line.substring(0, eq).trim(), line.substring(eq + 1).trim());
            }
        } catch (Throwable t) {
            t.printStackTrace();
        }
    }

    @Override
    public String homeContent(boolean filter) {
        // 分类先落地, 列表失败不拖累主页
        StringBuilder sb = new StringBuilder();
        sb.append("{\"class\":[");
        boolean first = true;
        for (Map.Entry<String, String> e : cates.entrySet()) {
            if (!first) sb.append(",");
            first = false;
            sb.append("{\"type_id\":\"").append(esc(e.getKey())).append("\",\"type_name\":\"").append(esc(e.getValue())).append("\"}");
        }
        sb.append("],\"filters\":{}");
        String listJson = "[]";
        try {
            listJson = videoList(fetch(listUrl("", "1")));
        } catch (Throwable t) {
            t.printStackTrace();
        }
        sb.append(",\"list\":").append(listJson).append("}");
        return sb.toString();
    }

    @Override
    public String homeVideoContent() {
        try {
            return "{\"list\":" + videoList(fetch(listUrl("", "1"))) + "}";
        } catch (Throwable t) {
            t.printStackTrace();
            return "{\"list\":[]}";
        }
    }

    @Override
    public String categoryContent(String tid, String pg, boolean filter, HashMap<String, String> extend) {
        try {
            String body = fetch(listUrl(tid, pg == null || pg.isEmpty() ? "1" : pg));
            return "{\"list\":" + videoList(body) + "," + paging(body, pg) + "}";
        } catch (Throwable t) {
            t.printStackTrace();
            return "{\"list\":[]}";
        }
    }

    @Override
    public String detailContent(List<String> ids) {
        try {
            if (ids == null || ids.isEmpty()) return "{\"list\":[]}";
            String body = fetch(join(apiUrl, "ac=videolist&ids=" + ids.get(0)));
            String block = firstVideo(body);
            if (block == null) return "{\"list\":[]}";
            String name = tag(block, "name");
            String pic = tag(block, "pic");
            String year = tag(block, "year");
            String area = tag(block, "area");
            String actor = tag(block, "actor");
            String director = tag(block, "director");
            String note = tag(block, "note");
            String des = tag(block, "des");
            String vid = tag(block, "id");

            // dd 按 flag 分组为播放源
            LinkedHashMap<String, List<String>> groups = new LinkedHashMap<>();
            Matcher m = DD.matcher(block);
            while (m.find()) {
                String flag = m.group(1) == null || m.group(1).isEmpty() ? "ckplayer" : m.group(1);
                List<String> eps = groups.get(flag);
                if (eps == null) { eps = new ArrayList<>(); groups.put(flag, eps); }
                String dd = m.group(2).trim();
                if (dd.isEmpty()) continue;
                for (String ep : dd.split("#")) {
                    ep = ep.trim();
                    if (ep.isEmpty()) continue;
                    eps.add(ep.contains("$") ? ep : "播放$" + ep);
                }
            }
            StringBuilder from = new StringBuilder();
            StringBuilder url = new StringBuilder();
            boolean first = true;
            for (Map.Entry<String, List<String>> e : groups.entrySet()) {
                if (!first) { from.append("$$$"); url.append("$$$"); }
                first = false;
                from.append(esc(e.getKey()));
                StringBuilder eps = new StringBuilder();
                boolean ef = true;
                for (String ep : e.getValue()) {
                    if (!ef) eps.append("#");
                    ef = false;
                    int dollar = ep.indexOf('$');
                    String epName = dollar > 0 ? ep.substring(0, dollar) : "播放";
                    String epUrl = dollar > 0 ? ep.substring(dollar + 1) : ep;
                    eps.append(esc(epName)).append("$").append(esc(epUrl));
                }
                url.append(eps);
            }
            StringBuilder sb = new StringBuilder();
            sb.append("{\"list\":[{\"vod_id\":\"").append(esc(vid)).append("\",\"vod_name\":\"").append(esc(name));
            sb.append("\",\"vod_pic\":\"").append(esc(pic)).append("\",\"vod_year\":\"").append(esc(year));
            sb.append("\",\"vod_area\":\"").append(esc(area)).append("\",\"vod_actor\":\"").append(esc(actor));
            sb.append("\",\"vod_director\":\"").append(esc(director)).append("\",\"vod_remarks\":\"").append(esc(note));
            sb.append("\",\"vod_content\":\"").append(esc(des.isEmpty() ? name : des));
            sb.append("\",\"vod_play_from\":\"").append(from).append("\",\"vod_play_url\":\"").append(url).append("\"}]}");
            return sb.toString();
        } catch (Throwable t) {
            t.printStackTrace();
            return "{\"list\":[]}";
        }
    }

    @Override
    public String playerContent(String flag, String id, List<String> vipFlags) {
        try {
            StringBuilder sb = new StringBuilder();
            sb.append("{\"parse\":\"0\",\"jx\":\"0\",\"playUrl\":\"\",\"url\":\"").append(esc(id == null ? "" : id));
            sb.append("\",\"header\":\"\",\"flag\":\"").append(esc(flag == null ? "" : flag)).append("\"}");
            return sb.toString();
        } catch (Throwable t) {
            t.printStackTrace();
            return "";
        }
    }

    @Override
    public String searchContent(String key, boolean quick, String pg) {
        try {
            String body = fetch(join(apiUrl, "ac=videolist&wd=" + URLEncoder.encode(key, "UTF-8")
                    + "&pg=" + (pg == null || pg.isEmpty() ? "1" : pg)));
            return "{\"list\":" + videoList(body) + "," + paging(body, pg) + "}";
        } catch (Throwable t) {
            t.printStackTrace();
            return "{\"list\":[]}";
        }
    }

    @Override
    public String searchContent(String key, boolean quick) {
        return searchContent(key, quick, "1");
    }

    // ---- 内部工具 ----

    private static String join(String api, String params) {
        return api + (api.contains("?") ? "&" : "?") + params;
    }

    private String listUrl(String tid, String pg) {
        return join(apiUrl, "ac=videolist" + (tid == null || tid.isEmpty() ? "" : "&t=" + tid) + "&pg=" + pg);
    }

    private String fetch(String url) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        if (conn instanceof HttpsURLConnection) {
            HttpsURLConnection https = (HttpsURLConnection) conn;
            https.setSSLSocketFactory(trustAll());
            https.setHostnameVerifier(trustName());
        }
        conn.setRequestMethod("GET");
        conn.setConnectTimeout(CONNECT_TIMEOUT);
        conn.setReadTimeout(READ_TIMEOUT);
        conn.setRequestProperty("User-Agent", UA);
        conn.setRequestProperty("Accept", "*/*");
        int code = conn.getResponseCode();
        if (code != 200) throw new Exception("HTTP " + code);
        BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), "UTF-8"));
        StringBuilder sb = new StringBuilder();
        char[] buf = new char[8192];
        int n;
        while ((n = reader.read(buf)) > 0) sb.append(buf, 0, n);
        reader.close();
        return sb.toString();
    }

    private static javax.net.ssl.SSLSocketFactory trustAll() throws Exception {
        TrustManager[] tm = new TrustManager[]{new X509TrustManager() {
            public void checkClientTrusted(X509Certificate[] chain, String authType) {
            }

            public void checkServerTrusted(X509Certificate[] chain, String authType) {
            }

            public X509Certificate[] getAcceptedIssuers() {
                return new X509Certificate[0];
            }
        }};
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(null, tm, new SecureRandom());
        return ctx.getSocketFactory();
    }

    private static HostnameVerifier trustName() {
        return new HostnameVerifier() {
            public boolean verify(String hostname, javax.net.ssl.SSLSession session) {
                return true;
            }
        };
    }

    // video 块内字段值(name/pic 等可能为 CDATA 或纯文本)
    private static String tag(String block, String name) {
        Matcher m = Pattern.compile("<" + name + ">(?:<!\\[CDATA\\[)?(.*?)(?:\\]\\]>)?</" + name + ">", Pattern.DOTALL).matcher(block);
        return m.find() ? m.group(1).trim() : "";
    }

    private static final Pattern DD = Pattern.compile("<dd(?:\\s+flag=\"([^\"]*)\")?\\s*>(?:<!\\[CDATA\\[)?(.*?)(?:\\]\\]>)?</dd>", Pattern.DOTALL);
    private static final Pattern VIDEO = Pattern.compile("<video>.*?</video>", Pattern.DOTALL);
    private static final Pattern PAGE = Pattern.compile("<list[^>]*pagecount=\"(\\d+)\"[^>]*recordcount=\"(\\d+)\"");

    private static String firstVideo(String body) {
        Matcher m = VIDEO.matcher(body);
        return m.find() ? m.group(0) : null;
    }

    private static String videoList(String body) {
        StringBuilder sb = new StringBuilder();
        sb.append("[");
        Matcher m = VIDEO.matcher(body);
        boolean first = true;
        while (m.find()) {
            String v = m.group(0);
            String id = tag(v, "id");
            if (id.isEmpty()) continue;
            if (!first) sb.append(",");
            first = false;
            sb.append("{\"vod_id\":\"").append(esc(id));
            sb.append("\",\"vod_name\":\"").append(esc(tag(v, "name")));
            sb.append("\",\"vod_pic\":\"").append(esc(tag(v, "pic")));
            sb.append("\",\"vod_remarks\":\"").append(esc(tag(v, "note")));
            sb.append("\",\"vod_year\":\"").append(esc(tag(v, "year"))).append("\"}");
        }
        sb.append("]");
        return sb.toString();
    }

    private static String paging(String body, String pg) {
        int page = 1;
        try {
            page = Integer.parseInt(pg);
        } catch (Throwable ignore) {
        }
        Matcher m = PAGE.matcher(body);
        if (!m.find()) return "\"page\":" + page + ",\"pagecount\":1,\"limit\":20,\"total\":0";
        return "\"page\":" + page + ",\"pagecount\":" + m.group(1) + ",\"limit\":20,\"total\":" + m.group(2);
    }

    private static String esc(String s) {
        if (s == null) return "";
        StringBuilder sb = new StringBuilder(s.length() + 8);
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '\\':
                    sb.append("\\\\");
                    break;
                case '"':
                    sb.append("\\\"");
                    break;
                case '\n':
                    sb.append("\\n");
                    break;
                case '\r':
                    sb.append("\\r");
                    break;
                case '\t':
                    sb.append("\\t");
                    break;
                default:
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        return sb.toString();
    }
}
