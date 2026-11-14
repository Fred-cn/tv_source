package com.github.catvod.spider;

import android.content.Context;

// JarLoader 强制要求本 jar 含 com.github.catvod.spider.Init 的静态 init(Context)。
// 本 jar 无全局状态需要初始化，空实现即可。
public class Init {

    public static void init(Context context) {
    }
}
