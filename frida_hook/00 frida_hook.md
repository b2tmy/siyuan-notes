---
title: 00 frida_hook
date: 2026-11-15T21:36:31+08:00
lastmod: 2026-11-15T22:05:44+08:00
---

# 00 frida_hook

# 00 frida_hook

Frida 动态插桩笔记。只记能直接复制去用的东西：环境命令、Java/Native 两层的 API、常见场景模板、以及踩过的坑。组织方式沿用 cryption 那套：0x00 结论，0x01 命令，0x02 模板，0x03 坑点。

> 原则：先确认进程、架构、so 加载时机，再谈 hook。挂不上的问题九成不在 JS 写错，而在版本不匹配、ClassLoader 不对、或者 hook 得太早/太晚。

## 目录

- 01 环境、frida-server 与命令行速查
- 02 Java 层：perform、use、overload、implementation
- 03 Native 层：Module、Interceptor、Memory、NativeFunction
- 04 常用 Hook 模板合集（SSL、root、反调试、参数打印）
- 05 排查：版本、ClassLoader、时机与对抗
- 06 CTF 逆向里的 Hook 题：题型、套路与解题脚本
- 07 CTF 里的 API Hook 题：IAT 与 Inline Hook 隐藏的加密函数

## 使用顺序

- 先把 01 的命令跑通：​`frida-ps -U`​ 能看到进程，​`frida -U -f 包名 -l xxx.js` 能加载脚本，再往下写 hook。
- Java 层题先看 02；so / JNI / 加固题看 03；要现成模板直接跳 04。
- 每写一个 hook，先只打印再改逻辑：​`console.log` 通了再动返回值，不要一上来就 replace。
- 挂不上或报错，先看 05，不要怀疑人生。
- 移动端真题翻 06；Windows 上改 API 权限、IAT / inline hook 藏加密函数的题，直接看 07。

## 版本对照

|层|入口|典型用途|
| --------| --------------------| ----------------------------|
|CLI|`frida`​ / ​`frida-trace`​ / ​`frida-ps`|起进程、attach、追函数|
|Java|`Java.perform`​ / ​`Java.use`|应用层方法、构造函数、重载|
|Native|`Interceptor.attach`​ / ​`Module`|so 导出函数、JNI、加密库|
|内存|`Memory`​ / ​`NativeFunction`|读写、扫描、调用任意地址|

说明：frida 客户端与 frida-server 大版本必须一致；Android 上 32 位与 64 位进程要分别确认架构，别拿 arm64 的地址去挂 arm 进程。
