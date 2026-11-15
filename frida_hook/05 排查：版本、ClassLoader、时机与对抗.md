---
title: 05 排查：版本、ClassLoader、时机与对抗
date: 2026-11-15T21:36:32+08:00
lastmod: 2026-11-15T21:36:32+08:00
---

# 05 排查：版本、ClassLoader、时机与对抗

# 05 排查：版本、ClassLoader、时机与对抗

挂不上、报错、进程崩，基本都能归到下面几类。按顺序排除，不要一上来就重写脚本。

## 0x00 版本不匹配

```text
Failed to load script: unable to communicate with remote frida-server
Failed to spawn: unable to connect to remote frida-server
```

- 客户端 ​`frida --version` 与服务端文件名里的版本必须同大版本，小版本可不同但有 API 差异。
- 服务端没起、端口没转发、设备没 root 都会表现为"连不上"。
- 排查顺序：​`adb shell ps -A | grep frida`​ → ​`frida-ps -U`​ → 再 ​`frida -U -f`。

## 0x01 找不到类 / ClassNotFoundException

```javascript
Java.perform(function () {
    // 先看类到底加载了没有
    console.log(Java.enumerateLoadedClassesSync()
        .filter(function (c) { return c.indexOf("example") >= 0; }));
});
```

- 类还没加载：hook 要等它被加载，用延迟或 hook ​`ClassLoader.loadClass`。
- 加固/动态加载：默认 loader 找不到，遍历 ​`Java.enumerateClassLoadersSync()`​ 切 ​`Java.classFactory.loader`。
- 类名写错：内部类用 ​`$`​，如 ​`com.example.app.Check$Result`；混淆过的包名先 dump 类列表。

## 0x02 方法重载没选对

```text
Error: verify(): argument types do not match any of:
    .overload('java.lang.String')
    .overload('int')
```

先打签名再挂：

```javascript
Java.use("com.example.app.Check").verify.overloads.forEach(function (o) {
    console.log(o.argumentTypes.map(function (t) { return t.className; }).join(", "));
});
```

数组写 ​`byte[]`​，基本类型写 ​`int`​ ​`long`​ ​`boolean`​，不要写 ​`java.lang.Integer`。

## 0x03 hook 时机太早

`-f`​ spawn 时脚本在 ​`Application`​ 初始化之前就跑完了，这时 ​`Java.use`​ 可能抛异常，​`Module.getExportByName` 返回 null。

```javascript
// 等 Java 环境就绪
Java.perform(function () {
    setTimeout(function () {
        var Cls = Java.use("com.example.app.Check");
        console.log(Cls);
    }, 1000);
});
```

```javascript
// 等 so 加载
function waitModule(name, cb) {
    var t = setInterval(function () {
        var m = Process.findModuleByName(name);
        if (m) { clearInterval(t); cb(m); }
    }, 200);
}
```

- `Java.perform` 本身会排队，但它只保证 ART 可用，不保证目标类已加载。
- 加固 App 的 dex 是运行时解密加载的，类出现得更晚，轮询比固定 sleep 稳。

## 0x04 hook 太晚

attach 到已经跑完初始化的进程，构造函数、​`onCreate`​ 这类一次性逻辑已经执行过。必须用 ​`-f` 冷启动，或者在 attach 之后主动调用一次目标方法把状态补回来。

## 0x05 进程崩溃

- `Interceptor.replace`​ 的参数/返回类型写错，寄存器错位。先用 ​`attach`​ + ​`retval.replace()`，确认稳定再换 replace。
- `retval.replace(1)`​ 用在指针返回值上会崩，指针要用 ​`ptr(0)`​ / ​`ptr(1)`。
- 32/64 位混用：拿 arm64 的 ​`base + offset` 去 arm 进程，地址全错，必崩。
- `Memory.writeByteArray`​ 写代码段前没 ​`Memory.protect`，直接 SIGSEGV。

## 0x06 应用检测 Frida

常见检测点：

- 进程名/端口：默认 ​`frida-server` 名字、27042 端口。
- 内存特征：​`frida-agent`​、​`gum-js-loop`​、​`/data/local/tmp` 下的文件。
- 线程名：​`gmain`​、​`gdbus`。

应对：服务端改名、换端口（​`-l 0.0.0.0:6666`​），必要时 hook ​`open`​/​`access`​ 把相关路径返回 -1。检测逻辑一般集中在启动阶段，用 ​`-f`​ 抢在前面挂 ​`File.exists`​、​`Runtime.exec`​、​`open`。

## 0x07 脚本本身的问题

- 语法：​`frida -U -f 包名 -l hook.js`​ 加载失败会直接打印行号，先本地 ​`node --check hook.js`。
- `this`​ 丢失：​`onEnter`​/​`onLeave`​ 里的 ​`this`​ 只在当前调用有效，跨阶段传值要显式挂到 ​`this` 上。
- 循环 hook 自己：​`implementation`​ 里调 ​`this.method()`​ 会再次进入 hook，导致递归爆栈；先存 ​`orig`​ 再用 ​`orig.call(this, ...)`。
- 日志太多：一次性打印所有参数会把 App 卡到 ANR，加过滤条件或计数上限。

## 0x08 快速自查表

```text
1. frida-ps -U 能看到进程吗
2. frida --version 与 frida-server 版本一致吗
3. Process.arch 与 so 架构一致吗
4. 目标类/模块在 enumerate 列表里吗
5. 重载签名打印了吗
6. 是 spawn 还是 attach，时机对吗
7. 改成只打印还崩吗
8. 换 replace 为 attach 还崩吗
9. 关掉其他 hook 单独跑这一条还崩吗
```
