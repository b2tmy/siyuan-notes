---
title: 03 Native 层：Module、Interceptor、Memory、NativeFunction
date: 2026-11-15T21:36:32+08:00
lastmod: 2026-11-15T21:36:32+08:00
---

# 03 Native 层：Module、Interceptor、Memory、NativeFunction

# 03 Native 层：Module、Interceptor、Memory、NativeFunction

Java 层靠类名，Native 层靠地址。地址来源只有三种：导出符号、​`base + 偏移`​、扫描到的指针。先确认 ​`Process.arch`，再决定用哪种参数读取方式。

## 0x00 定位模块与符号

```javascript
console.log(Process.arch, Process.pointerSize);   // arm64 / 8

var mod = Process.getModuleByName("libnative.so");
console.log(mod.base, mod.size, mod.path);

// 导出符号
var p = Module.getExportByName("libnative.so", "Java_com_example_app_Check_verify");
// null 表示在所有已加载模块里找
var strcmp = Module.getExportByName(null, "strcmp");

// 符号不存在时按 IDA 偏移算
var func = Process.getModuleByName("libnative.so").base.add(0x1A2C);
```

- `.add(0x1A2C)`​ 里的偏移取 IDA 的 **函数起始地址 - so 基址**，不是文件偏移。
- 找不到模块说明 so 还没加载；​`Process.enumerateModulesSync()`​ 确认，或在 ​`dlopen` 之后再做。

## 0x01 Interceptor.attach：最常用

```javascript
var addr = Module.getExportByName("libnative.so", "check_flag");

Interceptor.attach(addr, {
    onEnter: function (args) {
        // arm64：x0..x7 对应 args[0]..args[7]，arm32 是 r0..r3
        this.p0 = args[0];
        this.p1 = args[1];
        console.log("arg0 ptr:", args[0]);
        console.log("arg0 int:", args[0].toInt32());
        console.log("arg0 str:", args[0].readUtf8String());
        console.log("arg1 bytes:", args[1].readByteArray(16));
        console.log("caller:", Thread.backtrace(this.context, Backtracer.ACCURATE)
            .map(DebugSymbol.fromAddress).join("\n"));
    },
    onLeave: function (retval) {
        console.log("ret:", retval.toInt32());
        retval.replace(1);          // 改返回值
    }
});
```

参数没有类型信息，全靠你自己判断：

- 指针 → ​`readUtf8String()`​ / ​`readByteArray(n)`​ / ​`readPointer()`
- 整数 → ​`toInt32()`​ / ​`toUInt32()`​ / ​`toInt64()`，注意有无符号
- 结构体 → ​`readPointer()`​ + 逐字段偏移，或 ​`Memory.readUtf8String(p)`

`onEnter`​ 里的 ​`this` 是每次调用独立的对象，用来跨 onEnter/onLeave 传值，别用外部全局变量。

## 0x02 改参数

```javascript
Interceptor.attach(addr, {
    onEnter: function (args) {
        // 把字符串参数换成自己的
        var fake = Memory.allocUtf8String("admin");
        args[0] = fake;
        // 整数参数直接赋值
        args[1] = ptr(0x10);
    },
    onLeave: function (retval) {
        retval.replace(ptr(0));     // 指针返回值用 ptr()
    }
});
```

给 ​`args[i]`​ 赋值只在 ​`onEnter` 阶段有效，改的是寄存器影子，函数真正读的是寄存器。

## 0x03 Interceptor.replace：整段换实现

```javascript
var addr = Module.getExportByName("libnative.so", "check_flag");

var replacement = new NativeCallback(function (p) {
    console.log("replaced, arg:", p.readUtf8String());
    return 1;
}, "int", ["pointer"]);

Interceptor.replace(addr, replacement);

// 恢复原实现
// Interceptor.revert(addr);
```

- 返回类型和参数类型必须和原函数一致，否则栈/寄存器会错，进程直接崩。
- 只改返回值优先用 ​`onLeave`​ 的 ​`retval.replace()`，比 replace 安全。

## 0x04 Memory：读写、分配、扫描

```javascript
var buf = Memory.alloc(64);                       // 分配（rw-）
Memory.writeUtf8String(buf, "hello");
console.log(Memory.readUtf8String(buf));

Memory.writeByteArray(buf, [0x41, 0x42, 0x43]);
console.log(Memory.readByteArray(buf, 3));
console.log(hexdump(buf, { length: 64, ansi: true }));

// 改保护后写代码段
Memory.protect(addr, 4, "rwx");
Memory.writeByteArray(addr, [0x1F, 0x20, 0x03, 0xD5]);   // nop

// 扫描特征码，?? 是通配
Memory.scan(mod.base, mod.size, "41 42 ?? 43 00", {
    onMatch: function (address, size) {
        console.log("match:", address, size);
    },
    onComplete: function () {
        console.log("scan done");
    }
});
```

`Memory.scan`​ 是异步的（​`scanSync` 会卡 UI 线程），大模块建议限定范围。

## 0x05 NativeFunction：主动调用

```javascript
var fn = new NativeFunction(
    Module.getExportByName("libnative.so", "decrypt"),
    "pointer",                       // 返回类型
    ["pointer", "int"]               // 参数类型
);

var out = Memory.alloc(256);
var res = fn(Memory.allocUtf8String("input"), 5);
console.log(res.readUtf8String());
```

常用类型字符串：​`void`​ ​`bool`​ ​`int`​ ​`uint`​ ​`long`​ ​`uint64`​ ​`float`​ ​`double`​ ​`pointer`​ ​`size_t`。

调用 JNI 函数时第一个参数是 ​`JNIEnv*`​：​`Java.vm.getEnv()` 拿到 env 指针再传进去。

## 0x06 so 加载时机：hook 在它加载之后

`frida -f`​ 启动时目标 so 往往还没加载，直接 ​`Module.getExportByName` 会拿到 null。两种写法：

```javascript
// 写法一：拦 dlopen，加载完再挂
var dlopen = Module.getExportByName(null, "android_dlopen_ext");
Interceptor.attach(dlopen, {
    onEnter: function (args) {
        this.path = args[0].readCString();
    },
    onLeave: function (retval) {
        if (this.path && this.path.indexOf("libnative.so") >= 0) {
            console.log("loaded:", this.path);
            hookNative();               // 这里再做 attach
        }
    }
});
```

```javascript
// 写法二：轮询等模块出现（简单粗暴，适合脚本调试）
function waitFor(name, cb) {
    var t = setInterval(function () {
        var m = Process.findModuleByName(name);
        if (m) { clearInterval(t); cb(m); }
    }, 100);
}
waitFor("libnative.so", function (m) {
    console.log("base:", m.base);
});
```

`dlopen`​ 也有同名导出，​`android_dlopen_ext` 在 Android 上更可靠；两个都挂不冲突。

## 0x07 JNI 动态注册：符号被 strip 时的出路

`RegisterNatives` 之后，函数名和 so 里没有对应导出符号，只能从注册表拿地址。

```javascript
// 找到 RegisterNatives 的地址（不同 Android 版本符号可能不同，先枚举）
var sym = null;
Process.getModuleByName("libart.so").enumerateSymbols().forEach(function (s) {
    if (s.name.indexOf("RegisterNatives") >= 0) {
        console.log(s.name, s.address);
        sym = s.address;
    }
});

if (sym) {
    Interceptor.attach(sym, {
        onEnter: function (args) {
            var methods = args[2];       // JNINativeMethod*
            var count = args[3].toInt32();
            for (var i = 0; i < count; i++) {
                var name = methods.add(i * Process.pointerSize * 3).readPointer().readCString();
                var sig  = methods.add(i * Process.pointerSize * 3 + Process.pointerSize).readPointer().readCString();
                var fn   = methods.add(i * Process.pointerSize * 3 + Process.pointerSize * 2).readPointer();
                console.log(name, sig, fn);
            }
        }
    });
}
```

拿到 ​`fn`​ 之后用 ​`Interceptor.attach(fn, ...)`，比猜导出名靠谱。

## 0x08 大小端与结构体读取

```javascript
var p = args[0];
console.log(p.readU32());            // 本机字节序
console.log(p.add(4).readU16());
console.log(p.add(8).readPointer().readUtf8String());

// 手动小端拼 32 位
var b = p.readByteArray(4);
var v = new Uint8Array(b);
var val = v[0] | (v[1] << 8) | (v[2] << 16) | (v[3] << 24);
```

ARM 默认小端；读网络序或 Java 的 DataInputStream 数据要手动 ​`>>` 拼。

## 0x09 把结果送回 Python

```javascript
// hook.js
rpc.exports = {
    dump: function (addrStr) {
        return Memory.readUtf8String(ptr(addrStr));
    }
};
```

```python
# run.py
import frida, sys

def on_message(msg, data):
    print(msg)

session = frida.get_usb_device().attach("com.example.app")
script = session.create_script(open("hook.js", encoding="utf-8").read())
script.on("message", on_message)
script.load()
print(script.exports_sync.dump("0x12345678"))
sys.stdin.read()
```

`send(obj)`​ 在 JS 侧发消息、Python 侧 ​`on_message`​ 收；大块二进制用第二个参数 ​`data` 传 ArrayBuffer，别塞进 JSON。
