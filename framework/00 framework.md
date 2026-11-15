---
title: 00 framework
date: 2026-11-15T22:53:20+08:00
lastmod: 2026-11-15T22:53:20+08:00
---

# 00 framework

# framework

Android 注入与 Hook 框架笔记。重点记三层东西：**注入层**（怎么进到 zygote / 目标进程）、**Hook 层**（Java 方法、native 函数怎么被改）、**隐藏层**（root 与框架痕迹怎么被检测、怎么藏）。先写 LSPosed 和 Zygisk，再横向对比其他框架。

> 原则：框架只是载体，能不能挂上取决于三件事——注入时机、目标进程的 ClassLoader/ABI、以及目标是否在检测你。先确认这三件，再谈写模块。

## 目录

- 01 LSPosed：Xposed 生态、模块结构、Hook API 与作用域
- 02 Zygisk：zygote 注入、模块生命周期、native hook
- 03 其他框架与选型：EdXposed、KernelSU、ZygiskNext、Pine、Dobby 等
- 04 最小可运行模块：LSPosed 与 Zygisk 各一套工程骨架
- 05 检测与对抗：root / 框架 / hook 的痕迹与隐藏思路

## 三层结构

```text
┌─────────────────────────────────────────────┐
│ 模块层   Xposed 模块 / Zygisk .so / Frida 脚本 │
├─────────────────────────────────────────────┤
│ 框架层   LSPosed / Zygisk / ZygiskNext / Riru │
├─────────────────────────────────────────────┤
│ Root 层  Magisk / KernelSU / APatch           │
└─────────────────────────────────────────────┘
```

- LSPosed 自己既可以跑在 Zygisk 上，也可以跑在 Riru 上。
- Zygisk 是 Magisk 内建的注入框架，KernelSU / APatch 上一般用 ZygiskNext 提供同等能力。
- 隐藏层（Shamiko、Zygisk Assistant）解决的是"框架被检测到"的问题，不是 Hook 本身。

## 版本与兼容（以官方 release 为准）

|组件|常见支持范围|备注|
| -------------| --------------------------------| -----------------------------|
|原版 Xposed|Android 4.4–8.1|停更，仅历史参考|
|EdXposed|Android 8–11|依赖 Riru，已停更|
|LSPosed|Android 8.1 起，覆盖到较新版本|Zygisk / Riru 两种模式|
|Magisk|Android 6+|24 起内置 Zygisk|
|KernelSU|GKI 内核设备|需要 ZygiskNext 才有 Zygisk|
|APatch|内核补丁方案|同上|

具体到某个 Android 版本能不能用，先看框架 release note，再看设备内核，不要照抄旧教程。

## 学习顺序

1. 先看 01，写一个只打印 ​`handleLoadPackage` 的 LSPosed 模块，确认能被加载。
2. 再看 02，写一个只打日志的 Zygisk 模块，确认 ​`preAppSpecialize` 能拿到包名。
3. 用 04 的工程骨架抄结构，别从零建 Gradle/CMake。
4. 遇到"模块不生效"，先查 05 的检测面，再查作用域与时机。

## 术语

- **zygote**：Android 所有应用进程的父进程，fork 出 app 进程。
- **specialize**：zygote fork 之后，子进程确定 uid/包名/ABI 的过程。
- **PLT/GOT**：动态链接的跳转表，native hook 常改这里。
- **inline hook**：直接改函数开头机器码，跳转到自己的实现。
- **art method**：ART 里 Java 方法的运行时结构，Java hook 改的是它的入口。
