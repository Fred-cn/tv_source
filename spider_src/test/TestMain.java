import com.github.catvod.spider.Msnii;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Arrays;

// JVM 验证 harness: 读 ext 文件跑全部接口, 输出到 stdout 供 python 校验
public class TestMain {

    public static void main(String[] args) throws Exception {
        byte[] raw = Files.readAllBytes(Paths.get(args[0]));
        String ext = new String(raw, StandardCharsets.UTF_8);

        Msnii sp = new Msnii();
        sp.init(null, ext);

        System.out.println("=====homeContent=====");
        System.out.println(sp.homeContent(true));
        System.out.println("=====homeVideoContent=====");
        System.out.println(sp.homeVideoContent());
        System.out.println("=====categoryContent tid=35 pg=1=====");
        System.out.println(sp.categoryContent("35", "1", false, null));
        System.out.println("=====categoryContent tid=35 pg=2=====");
        System.out.println(sp.categoryContent("35", "2", false, null));
        System.out.println("=====detailContent=====");
        System.out.println(sp.detailContent(Arrays.asList("258583")));
        System.out.println("=====searchContent=====");
        System.out.println(sp.searchContent("女優", false, "1"));
        System.out.println("=====playerContent=====");
        System.out.println(sp.playerContent("ckplayer",
                "https://video22.msn17.com/video/20220401/c698c56ea413692f418eb489755c0514/index.m3u8", null));
    }
}
