---
title: 03 其他框架与选型：root 层、注入层、Hook 库
date: 2026-11-15T22:53:21+08:00
lastmod: 2026-11-15T22:53:21+08:00
---

# 03 其他框架与选型：root 层、注入层、Hook 库

# 03 其他框架与选型：root 层、注入层、Hook 库

LSPosed 和 Zygisk 解决的是"进得去、改得动"，但生态里还有几层东西要认识：root 方案、注入方案、隐藏方案、以及各种 Hook 库。这一篇把它们摆在一起，给一个按场景选型的参照。

## 0x00 分层看生态

```text
Root 层     Magisk / KernelSU / APatch
注入层      Zygisk / ZygiskNext / Riru（历史）/ LSPosed
Hook 层     Xposed API（LSPosed）、Zygisk native、Frida
Hook 库     Pine / YAHFA / SandHook / Dobby / ShadowHook / bhook / xhook
隐藏层      Shamiko / Zygisk Assistant / DenyList
```

- 换 root 方案，注入层可能跟着换：KernelSU 没有内建 Zygisk，要装 ZygiskNext。
- 隐藏层只解决"被检测"，不提供 Hook 能力，但不开它很多应用直接拒绝运行。

## 0x01 Root 方案

|方案|原理|特点|适用|
| ----------| --------------------------------------| -----------------------| ------------------------|
|Magisk|patch boot.img，用户态 su + 模块系统|生态最全，Zygisk 内建|大多数设备|
|KernelSU|内核态 su，GKI 内核模块|更隐蔽，需内核支持|GKI 设备、想少改用户态|
|APatch|内核补丁 + 用户态|介于两者之间|部分机型|

三者都能开模块目录 ​`/data/adb/modules`，Zygisk 类模块在 KernelSU/APatch 上要靠 ZygiskNext 提供运行时。

## 0x02 注入与 Hook 框架

|名称|层|需要 root|现状|适合|
| ------------------------| -------------| ----------------------| ---------------| ------------------------------|
|原版 Xposed|Java|是|停更（≤8.1）|只做历史参考|
|EdXposed|Java|是（Riru）|停更|老设备/老模块|
|LSPosed|Java|是（Zygisk/Riru）|活跃|Java 层 Hook 首选|
|VirtualXposed / TaiChi|Java|否|维护少|不想 root 的临时验证|
|Zygisk|native|是（Magisk）|内建|早期注入、native hook|
|ZygiskNext|native|是（KSU/APatch）|活跃|给非 Magisk root 补 Zygisk|
|Riru|native|是|停更|只出现在旧教程里|
|Frida|动态插桩|视场景|活跃|调试、抓参数、快速验证|
|Substrate|native/Java|是（iOS/老 Android）|历史|iOS 生态参考|
|Whale|多方案|否/是|活跃|免 root 或 root 的 Java Hook|

选择建议：

- 只想改 Java 方法、要稳定：**LSPosed**。
- 要在 App 启动前介入、或改 native：**Zygisk**（Magisk）或 **ZygiskNext**（KSU/APatch）。
- 只是临时看参数、不写模块：**Frida** 更快。
- 设备不能 root：VirtualXposed/Whale 这类免 root 方案，兼容性会差很多。

## 0x03 Hook 库

### Java 层

|库|特点|
| --------------| ------------------------------------------|
|Pine|轻量，API 简单，适合自己写一套 hook 引擎|
|YAHFA|老牌 ART hook，方法替换|
|SandHook|高性能 ART hook，支持较新 Android|
|LSPosed 内置|直接用 Xposed API，最省事|

### Native 层

|库|特点|
| ------------| ---------------------------------------|
|Dobby|跨平台 inline hook，Android/iOS/Linux|
|ShadowHook|字节开源的 inline hook，支持多架构|
|bhook|轻量 inline hook|
|xhook|PLT/GOT hook，适合挂导入函数|

写 Zygisk 模块时，PLT hook 优先（​`Api::pltHookRegister` 或 xhook），需要挂内部函数再上 inline hook（Dobby/ShadowHook）。

## 0x04 组合方式

```text
Magisk + Zygisk + LSPosed        → 最常见，Java + native 都能覆盖
KernelSU + ZygiskNext + LSPosed  → 非 Magisk 设备的等价组合
Magisk + Zygisk + 自写 .so       → 只要 native 能力，不需要 Xposed
Frida + spawn                    → 不落模块，临时分析
```

## 0x05 选型清单

1. 设备能 root 吗？不能 → 免 root 方案（Whale/VirtualXposed），预期放低。
2. 要改的是 Java 还是 native？Java → LSPosed；native → Zygisk 模块。
3. 需要多早介入？App 代码之前 → Zygisk ​`preAppSpecialize`；普通方法 → LSPosed 足够。
4. 目标有检测吗？有 → 先看 05，隐藏层往往比 Hook 本身更费时间。
5. 只是分析一次？→ Frida，别写模块。

## 0x06 常见误区

- **以为装了 LSPosed 就能 hook 所有应用**：作用域、加固、检测都会挡。
- **以为 Zygisk 一定比 LSPosed 强**：两者层级不同，Java Hook 用 LSPosed 更省事。
- **混用 Riru 与 Zygisk 模块**：老模块可能不兼容新注入层，报错先看模块说明。
- **忽略 root 隐藏**：很多应用检测到 root 就直接退出，跟 Hook 写得好不好无关。
- **在模拟器上验证真机行为**：ABI、内核、SELinux 都不一样。
