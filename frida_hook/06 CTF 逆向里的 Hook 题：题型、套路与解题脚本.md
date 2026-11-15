---
title: 06 CTF 逆向里的 Hook 题：题型、套路与解题脚本
date: 2026-11-15T22:01:26+08:00
lastmod: 2026-11-15T22:05:10+08:00
---

# 06 CTF 逆向里的 Hook 题：题型、套路与解题脚本

# 06 CTF 逆向里的 Hook 题：题型、套路与解题脚本

> 范围说明：本篇是 Android / Frida 侧。如果你的题目是 Windows 上改系统函数权限、用 IAT 或 inline hook 把隐藏加密函数挂进 ​`memcmp`​ 这类 API，直接看 **07 CTF 里的 API Hook 题**。

Hook 本身不是一种题型，而是逆向题的取证手段：程序知道答案，但答案藏在校验函数里、藏在运行时解密的字符串里、藏在被检测挡住的分支后面。这篇按"拿到题先判断什么、再决定 hook 还是 patch、最后怎么把 flag 逼出来"的顺序整理，所有脚本都是能直接改包名套用的骨架。

> 原则：hook 是过程，flag 才是结果。能把校验逻辑静态看出来就别 hook；hook 只用来拿运行时才存在的东西——解密后的明文、动态注册的函数地址、被反调试挡住的那条路径。

## 0x00 题型盘点与判断树

CTF 里和 hook 有关的题，基本落在这五类：

|类型|特征|主攻手段|
| -------------------| -----------------------------------------------------| --------------------------------|
|Java 校验|apk 可反编译，​`check()`​ / ​`verify()` 里逐字符比较|`Java.use`​ + ​`implementation` 打印参数|
|Native 校验|`System.loadLibrary`​ + ​`native` 方法，或纯 so 程序|`Interceptor.attach` 打参数/返回值|
|动态注册|`RegisterNatives`​，so 里搜不到 ​`Java_xxx` 符号|枚举 libart，拿函数指针再挂|
|反调试 / 反 Frida|启动就退出、​`ptrace`​、扫 ​`/proc/self/maps`、检测端口|先绕检测，再 hook|
|反 hook 题|题目本身检测你是否挂了 hook，要求"不被发现地"改行为|patch 检测点，或 hook 检测函数|

判断顺序（每一步都能砍掉一半工作量）：

1. 文件是 apk 还是 elf？apk 先 ​`jadx`，elf 直接 IDA。
2. 有没有 ​`lib/arm64-v8a/*.so`？有就先怀疑 native 校验。
3. 字符串里有没有 ​`frida`​、​`ptrace`​、​`/proc/self/maps`​、​`27042`？有就是反调试题。
4. 类名反编译出来是 ​`a.a.a` 这种？大概率加固，先脱壳或走 ClassLoader。
5. 校验通过后只弹一个 Toast？那 flag 可能是输入本身，也可能是程序算出来的——看比较的两个操作数。

## 0x01 标准解题流程

```text
1. adb install，随便输一个值，记住提示文案（wrong / try again / flag is）
2. jadx 全局搜索这段文案，往上找调用方，定位校验函数
3. 判断校验发生在 Java 还是 native（native 方法声明 / System.loadLibrary）
4. 先只打印：hook 参数、返回值、调用栈，确认输入怎么流动
5. 再决定：改返回 true、dump 明文、还是 patch 字节
6. 拿到候选后回代原程序，看到 success 才算完
7. 记录参数（包名、类名、方法签名、so 名、偏移），写进复盘
```

先打印再改逻辑，是这类题唯一不会翻车的顺序。很多题 hook 返回 true 之后只是"界面显示成功"，flag 并没有出现——因为 flag 是程序自己算出来的，不是你的输入。

## 0x02 例 1：Java 逐字符校验

题目结构通常长这样：

```java
public class Check {
    public static boolean verify(String s) {
        if (s.length() != 22) return false;
        for (int i = 0; i < 22; i++) {
            if ((s.charAt(i) ^ 0x13) != TARGET[i]) return false;
        }
        return true;
    }
}
```

脚本（先打印，不改逻辑）：

```javascript
Java.perform(function () {
    var Check = Java.use("com.example.app.Check");

    Check.verify.overload("java.lang.String").implementation = function (s) {
        console.log("[*] verify(" + s + "), len=" + s.length);
        var ret = this.verify(s);
        console.log("[*] ret = " + ret);
        return ret;
    };
});
```

输出里能看到每次调用的输入和结果。如果只想知道"输入对不对"，把 ​`return ret`​ 改成 ​`return true`​ 即可；但想拿 flag，就得看 ​`TARGET`：

```javascript
Java.perform(function () {
    var Check = Java.use("com.example.app.Check");
    console.log(Check.TARGET.value);           // 静态数组
    // 或者实例字段：inst.TARGET.value
});
```

拿到 ​`TARGET`​ 后按同样的异或反推输入，这才是 flag。**只改返回值拿不到 flag**，这是新手最常见的空手而归。

## 0x03 例 2：Native 校验，参数是 jstring

so 里的函数签名：

```c
JNIEXPORT jboolean JNICALL Java_com_example_app_Check_verify(JNIEnv *env, jclass clazz, jstring input)
```

hook 导出符号，​`args[2]`​ 是 ​`jstring`，要转成字符串：

```javascript
Java.perform(function () {
    var addr = Module.getExportByName("libnative.so", "Java_com_example_app_Check_verify");
    var env = Java.vm.getEnv();

    Interceptor.attach(addr, {
        onEnter: function (args) {
            try {
                this.input = env.getStringUtfChars(args[2], null).readUtf8String();
                console.log("[*] verify(" + this.input + ")");
            } catch (e) {
                console.log("[-] read jstring failed: " + e);
            }
            console.log(Thread.backtrace(this.context, Backtracer.ACCURATE)
                .map(DebugSymbol.fromAddress).join("\n"));
        },
        onLeave: function (retval) {
            console.log("[*] ret = " + retval.toInt32());
            retval.replace(1);                 // 需要"通过"时再打开
        }
    });
});
```

几个细节：

- `getStringUtfChars`​ 返回的是 ​`const char*`​，拿完可以 ​`ReleaseStringUTFChars`，CTF 里一般不管。
- 中文/宽字符要用 ​`getStringChars`​（UTF-16），读完 ​`readUtf16String()`。
- 如果 so 里没有 ​`Java_...` 符号，说明是动态注册，走下一节。

## 0x04 例 3：RegisterNatives，符号被 strip

`JNI_OnLoad` 里注册的函数在 so 的符号表里没有名字，只能从注册表里捞地址：

```javascript
Java.perform(function () {
    var libart = Process.getModuleByName("libart.so");
    var reg = null;

    libart.enumerateSymbols().forEach(function (s) {
        if (s.name.indexOf("RegisterNatives") >= 0) {
            console.log("[*] " + s.name + " @ " + s.address);
            reg = s.address;
        }
    });

    if (!reg) { console.log("[-] RegisterNatives not found"); return; }

    Interceptor.attach(reg, {
        onEnter: function (args) {
            var methods = args[2];
            var count = args[3].toInt32();
            console.log("[*] RegisterNatives count=" + count);

            for (var i = 0; i < count; i++) {
                var base = methods.add(i * Process.pointerSize * 3);
                var name = base.readPointer().readCString();
                var sig  = base.add(Process.pointerSize).readPointer().readCString();
                var fn   = base.add(Process.pointerSize * 2).readPointer();
                console.log("    " + name + sig + " -> " + fn);

                Interceptor.attach(fn, {
                    onEnter: function (a) {
                        console.log("[+] " + name + " called, arg0=" + a[2]);
                    },
                    onLeave: function (r) {
                        console.log("[+] " + name + " ret=" + r);
                    }
                });
            }
        }
    });
});
```

- `JNINativeMethod`​ 是三个指针：​`name`​、​`signature`​、​`fnPtr`​，按 ​`pointerSize * 3` 步进。
- 不同 Android 版本的符号名可能是 ​`_ZN3art3JNI15RegisterNativesEP7_JNIEnvP7_jclassPK15JNINativeMethodi`​，所以用 ​`indexOf` 模糊匹配。
- 挂上之后同样能 ​`Interceptor.replace(fn, ...)`，但类型必须自己按签名写对，写错直接崩。

## 0x05 例 4：反调试 / 反 Frida

这类题的表现是：frida 一 attach 进程就退出，或者界面提示"检测到调试"。

先分清检测发生在哪一层：

```javascript
// 看进程里有没有可疑线程和模块
console.log(Process.enumerateThreadsSync().map(function (t) {
    return t.id + ":" + (t.name || "");
}).join("\n"));
console.log(Process.enumerateModulesSync().map(function (m) { return m.name; }).join("\n"));
```

常见检测点与对应处理：

```javascript
// 1) ptrace 自附加，返回 -1 让它以为附加失败
var ptrace = Module.getExportByName(null, "ptrace");
Interceptor.replace(ptrace, new NativeCallback(function () {
    console.log("[*] ptrace blocked");
    return 0;
}, "int", ["int", "int", "pointer", "pointer"]));

// 2) 字符串检测：strstr("frida") / strstr("gum")
var strstr = Module.getExportByName(null, "strstr");
Interceptor.attach(strstr, {
    onEnter: function (args) {
        this.needle = args[1].readCString();
    },
    onLeave: function (retval) {
        if (this.needle && /frida|gum|magisk|xposed/i.test(this.needle)) {
            console.log("[*] hide strstr: " + this.needle);
            retval.replace(ptr(0));
        }
    }
});

// 3) 扫 /proc/self/maps、检测端口：拦 open/access
var open = Module.getExportByName(null, "open");
Interceptor.attach(open, {
    onEnter: function (args) {
        this.path = args[0].readCString();
    },
    onLeave: function (retval) {
        if (this.path && /maps|status|27042|frida/i.test(this.path)) {
            console.log("[*] open(" + this.path + ") -> -1");
            retval.replace(-1);
        }
    }
});
```

顺序建议：

1. 先改 frida-server 名字、换端口（​`-l 0.0.0.0:6666`），很多检测只认默认值。
2. 再 hook 字符串和文件类检测。
3. 最后才 hook ​`ptrace`，因为它影响面大。
4. 检测在 ​`.init_array`​ 或 ​`JNI_OnLoad`​ 里时，用 ​`-f`​ spawn，并在 ​`dlopen` 回调里尽早挂。

## 0x06 例 5：拿运行时解密出来的字符串

加固题、so 题常见：字符串在 so 里是密文，运行时解密到堆上，用完就释放。思路是"在它被用掉的那一刻截胡"。

```javascript
// 已知 so 里有个 decrypt(char *in, char *out) 之类的函数
var addr = Module.getExportByName("libnative.so", "decrypt");
Interceptor.attach(addr, {
    onEnter: function (args) {
        this.out = args[1];            // 输出缓冲区
        console.log("[in ] " + args[0].readUtf8String());
    },
    onLeave: function () {
        try {
            console.log("[out] " + this.out.readUtf8String());
        } catch (e) {
            console.log("[out] " + hexdump(this.out, { length: 32 }));
        }
    }
});
```

如果不知道解密函数在哪，就从下游反推——一般解密完都会送进 ​`strcmp`​ / ​`memcmp`​ / ​`strlen`：

```javascript
["strcmp", "memcmp", "strlen"].forEach(function (name) {
    var p = Module.findExportByName(null, name);
    if (!p) return;
    Interceptor.attach(p, {
        onEnter: function (args) {
            console.log("[" + name + "] " + args[0].readUtf8String() + " | " + args[1].readUtf8String());
        }
    });
});
```

也可以直接在内存里搜特征：

```javascript
var mod = Process.getModuleByName("libnative.so");
Memory.scan(mod.base, mod.size, "66 6c 61 67 7b", {   // "flag{"
    onMatch: function (a) { console.log("[scan] " + a.readUtf8String()); }
});
```

## 0x07 hook 还是 patch：决策表

|场景|选择|原因|
| -------------------------------| ------------------------| -----------------------------------|
|只要"通过"校验，flag 就是输入|hook 返回 true|最快，改一行|
|flag 是程序算出来的|dump 明文 / 读目标数组|改 true 只会显示成功，拿不到 flag|
|有服务端校验或签名|必须还原算法|本地 hook 不影响远端|
|反调试导致 hook 不稳|静态 patch so 偏移|一劳永逸，还不用起服务端|
|题目要求交 hook 脚本|按题面 API 写|别自作聪明改二进制|
|时间只剩十分钟|`objection`​ + ​`frida-trace`|先看调用，再决定|

objection 一把梭：

```bash
objection -g com.example.app explore
# 里面执行
android hooking list classes
android hooking watch class_method com.example.app.Check.verify --dump-args --dump-return
android hooking watch class com.example.app.Check
```

## 0x08 常见坑

- **改 true 但没 flag**：flag 是程序算的，去看比较点两侧的操作数。
- **校验被调用成百上千次**：加计数或条件过滤，别让日志把终端刷爆。
- **JNI 字符串乱码**：​`getStringUtfChars`​ 与 ​`getStringChars` 一个是 UTF-8 一个是 UTF-16。
- **找不到类**：加固/多 dex，先 ​`Java.enumerateClassLoadersSync()` 切 loader。
- **只挂了一个架构**：​`arm64-v8a`​ 和 ​`armeabi-v7a`​ 的 so 偏移完全不同，​`Process.arch` 先确认。
- **hook 后进程秒退**：可能是检测，也可能是 ​`implementation`​ 里递归调用了自己（先存原方法再 ​`call`）。
- **模拟器跑 x86**：so 只有 arm 版本，换真机或找 x86 版本，别硬转译。
- **题目要求"不被检测地 hook"** ：先 patch 检测函数，再挂业务函数，顺序反了必被踢。

## 0x09 一页式解题模板

```javascript
"use strict";

var PKG = "com.example.app";
var CLS = "com.example.app.Check";
var LIB = "libnative.so";

Java.perform(function () {
    // 1) 打印类里所有方法，确认签名
    var C = Java.use(CLS);
    C.class.getDeclaredMethods().forEach(function (m) {
        console.log(m.getName());
    });

    // 2) 只打印，不改逻辑
    var orig = C.verify.overload("java.lang.String");
    orig.implementation = function (s) {
        console.log("[java] verify(" + s + ")");
        var r = orig.call(this, s);
        console.log("[java] -> " + r);
        return r;
    };

    // 3) native 侧同样先打印
    var addr = Module.findExportByName(LIB, "check_flag");
    if (addr) {
        Interceptor.attach(addr, {
            onEnter: function (args) {
                console.log("[native] arg0=" + args[0].readUtf8String());
            },
            onLeave: function (retval) {
                console.log("[native] ret=" + retval.toInt32());
            }
        });
    }
});

// 4) 记录：包名 / 类名 / 方法签名 / so 名 / 偏移 / 是否加固 / 最终 FLAG
```

## 0x0a 复盘表

```text
题目：
类型：Java / Native / 动态注册 / 反调试 / 反 hook
包名与进程：
校验位置：类.方法 或 so!函数 / 偏移
输入长度与格式：
关键常量：
是否加固：
hook 点：
patch 点（如果有）：
FLAG：
踩坑：
```

## 0x0b 参考

- [CTF 移动安全（Android）题型解析](https://cloud.tencent.com.cn/developer/article/2587063)
- [Frida_Mobile_CTF_Solutions](https://github.com/brkn45/Frida_Mobile_CTF_Solutions)
- [Mobile Hacking Lab Writeups](https://github.com/mehmetfarisacar/Mobile-Hacking-Lab-Writeups)

0x09 骨架的可运行版本在 ​`scripts/ctf_hook_solution.js`​：改 CONFIG 里的类名、方法签名、so 名和函数名，​`forceReturn` 先留 null 只打印，确认打得到再填返回值。
