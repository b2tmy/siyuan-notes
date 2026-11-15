---
title: 05 检测与对抗：root、框架与 hook 的痕迹
date: 2026-11-15T22:53:22+08:00
lastmod: 2026-11-15T22:53:22+08:00
---

# 05 检测与对抗：root、框架与 hook 的痕迹

# 05 检测与对抗：root、框架与 hook 的痕迹

模块写好了不代表能用：目标应用会检测 root、检测框架、检测 hook。这一篇把常见检测面列清楚，再讲对应的隐藏思路。顺序很重要——**先藏 root，再藏框架，最后才谈 hook 本身**。

## 0x00 检测面总览

|层面|目标应用会看什么|典型手段|
| ------| ------------------------------------| ---------------------------------|
|root|su 文件、Magisk 目录、属性、挂载表|`File.exists`​、​`Runtime.exec("which su")`​、​`/proc/mounts`|
|框架|LSPosed/Zygisk/Riru 的 so 与目录|扫 ​`/proc/self/maps`、类名探测|
|Hook|函数头被改、GOT 项异常|读内存比对、CRC 校验|
|环境|模拟器、调试器、VPN/代理|Build 属性、TracerPid、网络接口|

## 0x01 root 检测

常见检查点：

```text
/system/bin/su、/system/xbin/su、/sbin/su
/data/adb/magisk、/data/adb/modules
ro.debuggable、ro.secure、ro.build.tags
/proc/mounts 里 magisk 相关挂载
pm list packages 里的 magisk 包名
```

隐藏思路的层次：

1. **DenyList / Shamiko**：把目标应用放进 DenyList，Shamiko 负责把 root 痕迹从该进程隐藏。
2. **随机包名**：Magisk 设置里随机化 Manager 包名，减少按包名扫描命中。
3. **hook 检测函数**：​`File.exists`​ 对敏感路径返回 false，​`Runtime.exec`​ 拦截 ​`su`​/​`ps` 命令。
4. **属性与挂载**：hook ​`SystemProperties.get`​、过滤 ​`/proc/mounts` 的读取结果。

```java
// LSPosed 里拦 File.exists（示例，按需加路径白名单）
XposedHelpers.findAndHookMethod(java.io.File.class, "exists", new XC_MethodHook() {
    @Override
    protected void afterHookedMethod(MethodHookParam param) {
        String path = ((java.io.File) param.thisObject).getAbsolutePath();
        if (path.contains("magisk") || path.endsWith("/su")) {
            param.setResult(false);
        }
    }
});
```

## 0x02 框架检测

LSPosed、Zygisk、Riru 都会在进程里留下痕迹：

- `/proc/self/maps`​ 里出现 ​`lsposed`​、​`zygisk`​、​`riru`​、​`libxposed` 等字符串。
- `de.robv.android.xposed.XposedBridge`​ 类能被 ​`Class.forName` 找到。
- 调用栈里出现框架的类名。
- `/data/adb/modules` 下能看到模块目录（root 权限下）。

对应的隐藏做法：

- 用 Shamiko / Zygisk Assistant 处理 maps 与挂载层面的痕迹。
- 模块自身避免在目标进程里注册显眼的类名/线程名。
- 对 ​`Class.forName("de.robv...")`​ 这类探测，直接 hook 让它抛 ​`ClassNotFoundException`。
- 有些检测会读 ​`/proc/self/maps`​，可以 hook ​`open`​/​`read` 或在 Java 层拦截读取。

## 0x03 hook 检测

- **inline hook 检测**：读目标函数前 16 字节，和磁盘上的原始字节比对；或对函数做 CRC。对策是用不修改函数头的方案（PLT/GOT），或把比对函数一起 hook。
- **GOT/PLT 检测**：检查 GOT 项是否指向合法模块区间。对策是 hook 检查函数，或在检查之后再做 hook。
- **ART 方法检测**：比对 ​`ArtMethod` 的 entry point 是否在预期区间。LSPosed 这类框架会处理，但自写 hook 要注意。
- **时间检测**：hook 前后耗时异常也可能被判定。

## 0x04 隐藏层组件

|组件|作用|备注|
| ------------------| -------------------------------| ----------------------|
|Magisk DenyList|对指定应用隐藏 root|基础能力，强度一般|
|Shamiko|强化隐藏，处理 maps/挂载/属性|常与 DenyList 配合|
|Zygisk Assistant|非 Magisk 环境的隐藏|KernelSU/APatch 常用|
|随机包名|降低按包名扫描命中|Magisk 设置里开|

顺序建议：先开 DenyList + Shamiko，确认目标能启动；再决定要不要写 hook 级隐藏。

## 0x05 对抗的基本思路

1. **先定位检测点**：用 Frida/LSPosed 打日志，看目标在退出前调用了哪些敏感 API（​`File.exists`​、​`exec`​、​`open`​、​`read`​、​`Class.forName`）。
2. **只改必要的返回值**：​`exists -> false`​、​`exec -> 空`​、​`forName -> 抛异常`，不要大范围伪造，容易引发别的崩溃。
3. **注意时序**：检测往往在 ​`Application.onCreate`​ 之前（​`attachBaseContext`​）就跑完了，模块要更早挂上（Zygisk ​`preAppSpecialize`）。
4. **保持一致性**：文件说不存在，但 ​`listFiles` 又能列出来，就会被交叉校验抓到。改一处要想到配套的 API。
5. **别在系统进程上试**：​`system_server` 崩了会直接重启，先在普通应用验证。

## 0x06 注意点

- 隐藏与检测是持续对抗，今天有效的方案下个版本可能就失效，别把某一版当永久结论。
- 不同 ROM（MIUI、HyperOS、ColorOS）检测点不一样，日志要按机型看。
- 关闭 SELinux、改系统分区这类操作会破坏设备完整性，尽量用框架提供的机制，不要手工改系统。
- 只在自己的设备/测试机上验证，模块里的路径、包名、签名都按自己的环境来。
