---
title: 01 环境、frida-server 与命令行速查
date: 2026-11-15T21:36:31+08:00
lastmod: 2026-11-15T21:36:31+08:00
---

# 01 环境、frida-server 与命令行速查

# 01 环境、frida-server 与命令行速查

这篇只放命令，不解释原理。设备上的 frida-server 跑起来、​`frida-ps` 能看到进程，后面才有得谈。

## 0x00 装什么

```bash
pip install frida frida-tools
frida --version
frida-ps --version
```

- 客户端版本记下来，服务端必须同大版本。查最新：​`pip index versions frida`​ 或 ​`frida --version`​ 对照 [frida releases](https://github.com/frida/frida/releases)。
- Android 服务端文件名形如 ​`frida-server-16.5.2-android-arm64.xz`，解压后是单个 ELF。

## 0x01 客户端命令

```bash
frida-ls-devices                 # 列出可用设备（local / usb / remote）
frida-ps -D                      # 列出设备
frida-ps -U                      # USB 设备上正在运行的进程
frida-ps -U -a                   # 正在运行的应用（带包名）
frida-ps -U -ai                  # 所有已安装应用
frida-ps -U | grep -i 关键字      # 找目标进程
frida-kill -U 12345              # 杀进程
frida-discover -U                # 枚举可 hook 的函数（旧工具，偶尔有用）
```

远程设备：

```bash
frida-ps -H 192.168.1.10:27042
frida -H 192.168.1.10:27042 -n 进程名 -l script.js
```

## 0x02 设备端 frida-server

```bash
adb push frida-server /data/local/tmp/
adb shell "chmod 755 /data/local/tmp/frida-server"

# root 设备直接起
adb shell "su -c '/data/local/tmp/frida-server &'"

# 非默认端口，降低被端口扫描型检测命中的概率
adb shell "su -c '/data/local/tmp/frida-server -l 0.0.0.0:1234 &'"
```

端口转发（USB 设备通常不需要，远程或模拟器要）：

```bash
adb forward tcp:27042 tcp:27042
adb forward tcp:27043 tcp:27043
```

确认服务端在跑：

```bash
adb shell "ps -A | grep frida"
frida-ps -U
```

- 设备重启后 frida-server 不会自启，重新执行启动命令。
- x86 模拟器要用 ​`frida-server-*-android-x86_64`​，装错架构会直接 ​`Exec format error`。

## 0x03 spawn 与 attach

```bash
# spawn：由 frida 拉起进程，能抢在 Application 初始化之前挂上
frida -U -f com.example.app -l hook.js --no-pause

# attach：附加到已经在跑的进程（按包名或 pid）
frida -U com.example.app -l hook.js
frida -U -p 12345 -l hook.js

# 只加载脚本、不交互
frida -U -f com.example.app -l hook.js --no-pause -q

# 输出同时写文件
frida -U -f com.example.app -l hook.js -o out.log
```

- `--no-pause`​ 不加的话，spawn 后会停在入口等你在 REPL 里敲 ​`%resume`。
- `-f`​ 用于冷启动，​`-n`​ 用于按名字 attach；​`-p` 按 pid。
- 脚本里想主动恢复：​`Java.perform`​ 之外用 ​`setImmediate`​，或 REPL 输入 ​`%resume`。

## 0x04 脚本加载与运行时

```bash
frida -U -f com.example.app -l a.js -l b.js      # 多个脚本按顺序加载
frida -U -f com.example.app --runtime=qjs -l hook.js   # 换运行时（默认 qjs，老环境用 v8）
frida -U -f com.example.app -l hook.js -e 'console.log(Process.arch)'
```

REPL 里常用：

```text
%resume          继续运行
%reload          重新加载脚本
%process         查看进程信息
%exit            退出
```

## 0x05 frida-trace：不改代码先看调用

```bash
# 追某个 so 里的导出函数
frida-trace -U -f com.example.app -I libnative.so -i "Java_*"

# 追 Java 方法，支持通配
frida-trace -U -f com.example.app -j 'com.example.app.*!*'

# 只看包含关键字的符号
frida-trace -U -f com.example.app -I libc.so -i "*open*"

# 附加到已运行进程
frida-trace -U -n com.example.app -j 'com.example.*!*password*'
```

- `-i`​ 匹配导出符号，​`-I`​ 限定模块；​`-j`​ 匹配 Java 方法；​`-X` 匹配 OCaml/ObjC。
- 生成 ​`__handlers__/` 目录，里面的 JS 可以直接改，是快速摸底的好起点。
- 追不到多半是符号被 strip 或模块还没加载，用 ​`-f`​ 并把 ​`-I` 换成加载后的时机。

## 0x06 常用组合

```bash
# 看某个 App 到底加载了哪些 so
frida -U -f com.example.app --no-pause -q -e 'Process.enumerateModules().forEach(m=>console.log(m.name, m.base, m.size))'

# 看当前进程架构，决定挂 arm 还是 arm64
frida -U -n com.example.app -q -e 'console.log(Process.arch, Process.pointerSize)'

# 列出所有已加载类，配合 grep 找目标
frida -U -n com.example.app -q -e 'Java.perform(()=>Java.enumerateLoadedClassesSync().filter(c=>/example/.test(c)).forEach(c=>console.log(c)))'
```
