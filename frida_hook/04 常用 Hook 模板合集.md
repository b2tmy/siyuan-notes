---
title: 04 常用 Hook 模板合集
date: 2026-11-15T21:36:32+08:00
lastmod: 2026-11-15T21:36:52+08:00
---

# 04 常用 Hook 模板合集

# 04 常用 Hook 模板合集

这片是复制粘贴区。每条先小范围验证（只打印），确认打到了再改逻辑。类名、包名、so 名按题目替换。

## 0x00 批量打印一个类的所有方法

```javascript
Java.perform(function () {
    var Cls = Java.use("com.example.app.Check");
    Cls.class.getDeclaredMethods().forEach(function (m) {
        var name = m.getName();
        var over = Cls[name];
        if (!over || !over.overloads) return;
        over.overloads.forEach(function (o) {
            var sig = o.argumentTypes.map(function (t) { return t.className; }).join(", ");
            console.log(name + "(" + sig + ")");
            o.implementation = function () {
                var args = Array.prototype.slice.call(arguments).join(", ");
                console.log("[*] " + name + "(" + args + ")");
                var r = o.apply(this, arguments);
                console.log("[*] " + name + " -> " + r);
                return r;
            };
        });
    });
});
```

类方法多的时候只挂含关键字的方法，避免把 App 拖死：

```javascript
if (name.toLowerCase().indexOf("check") < 0) return;
```

## 0x01 打印调用栈 + 参数

```javascript
function stackTrace() {
    var Log = Java.use("android.util.Log");
    var Ex = Java.use("java.lang.Exception");
    return Log.getStackTraceString(Ex.$new());
}

Java.perform(function () {
    var Cls = Java.use("com.example.app.Check");
    var m = Cls.verify.overload("java.lang.String");
    m.implementation = function (s) {
        console.log("verify:", s);
        console.log(stackTrace());
        return m.call(this, s);
    };
});
```

Native 侧等价物：

```javascript
Interceptor.attach(addr, {
    onEnter: function (args) {
        console.log(Thread.backtrace(this.context, Backtracer.ACCURATE)
            .map(DebugSymbol.fromAddress).join("\n"));
    }
});
```

## 0x02 SSL Pinning 通用绕过

系统 TrustManager（覆盖大多数 OkHttp/HttpURLConnection）：

```javascript
Java.perform(function () {
    var TrustManagerImpl = Java.use("com.android.org.conscrypt.TrustManagerImpl");
    TrustManagerImpl.verifyChain.implementation = function (untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
        console.log("[*] bypass TrustManagerImpl: " + host);
        return untrustedChain;
    };

    var X509TrustManager = Java.use("javax.net.ssl.X509TrustManager");
    var SSLContext = Java.use("javax.net.ssl.SSLContext");
    var TrustManager = Java.registerClass({
        name: "com.example.FakeTrustManager",
        implements: [X509TrustManager],
        methods: {
            checkClientTrusted: function (chain, authType) {},
            checkServerTrusted: function (chain, authType) {},
            getAcceptedIssuers: function () { return []; }
        }
    });
    var ctx = SSLContext.getInstance("TLS");
    ctx.init(null, [TrustManager.$new()], null);
    SSLContext.init.overload("[Ljavax.net.ssl.KeyManager;", "[Ljavax.net.ssl.TrustManager;", "java.security.SecureRandom")
        .implementation = function (km, tm, sr) {
            console.log("[*] SSLContext.init hooked");
            this.init(km, [TrustManager.$new()], sr);
        };
});
```

OkHttp 的 ​`CertificatePinner`：

```javascript
Java.perform(function () {
    try {
        var Pinner = Java.use("okhttp3.CertificatePinner");
        Pinner.check.overload("java.lang.String", "java.util.List").implementation = function (host, peers) {
            console.log("[*] CertificatePinner.check: " + host);
        };
        Pinner.check$okhttp.overload("java.lang.String", "kotlin.jvm.functions.Function0").implementation = function (host, f) {
            console.log("[*] check$okhttp: " + host);
        };
    } catch (e) {
        console.log("no okhttp: " + e);
    }
});
```

HostnameVerifier：

```javascript
Java.perform(function () {
    var HostnameVerifier = Java.use("javax.net.ssl.HostnameVerifier");
    var OkHostnameVerifier = Java.use("okhttp3.internal.tls.OkHostnameVerifier");
    OkHostnameVerifier.verify.overload("java.lang.String", "javax.net.ssl.SSLSession").implementation = function (h, s) {
        return true;
    };
});
```

- 这几个类名随版本变（​`okhttp3.internal.tls.OkHostnameVerifier`​、​`com.android.okhttp...`​），​`Java.available` 后先枚举类名再挂。
- 双向认证要同时替换客户端证书，只绕过校验不够。

## 0x03 Root / Frida 检测绕过

```javascript
Java.perform(function () {
    // File.exists
    var File = Java.use("java.io.File");
    File.exists.implementation = function () {
        var path = this.getAbsolutePath();
        if (/su$|magisk|frida|xposed|superuser/i.test(path)) {
            console.log("[*] hide " + path);
            return false;
        }
        return this.exists();
    };

    // Runtime.exec / ProcessBuilder 检测 ps
    var Runtime = Java.use("java.lang.Runtime");
    Runtime.exec.overload("java.lang.String").implementation = function (cmd) {
        if (cmd.indexOf("ps") >= 0 || cmd.indexOf("frida") >= 0) {
            console.log("[*] block exec: " + cmd);
            return this.exec("echo");
        }
        return this.exec(cmd);
    };

    // Build.TAGS
    var Build = Java.use("android.os.Build");
    console.log("TAGS:", Build.TAGS.value);
});
```

更省事的做法是把 frida-server 改名、换端口，从源头躲掉名字和端口扫描：

```bash
adb shell "su -c 'cp /data/local/tmp/frida-server /data/local/tmp/fs-helper'"
adb shell "su -c '/data/local/tmp/fs-helper -l 0.0.0.0:6666 &'"
frida -H 127.0.0.1:6666 -f com.example.app -l hook.js
```

## 0x04 反调试：ptrace / 时间检测

```javascript
// hook libc 的 ptrace，让反调试以为没被跟踪
var ptrace = Module.getExportByName(null, "ptrace");
Interceptor.replace(ptrace, new NativeCallback(function (req, pid, addr, data) {
    console.log("[*] ptrace blocked, req=" + req);
    return 0;
}, "int", ["int", "int", "pointer", "pointer"]));
```

`strstr`​ / ​`strcmp` 类字符串检测：

```javascript
var strstr = Module.getExportByName(null, "strstr");
Interceptor.attach(strstr, {
    onEnter: function (args) {
        this.a = args[0].readCString();
        this.b = args[1].readCString();
    },
    onLeave: function (retval) {
        if (this.b && /frida|gum|magisk/i.test(this.b)) {
            retval.replace(ptr(0));
        }
    }
});
```

时间差检测（​`clock_gettime`​ 返回异常）一般直接让 ​`gettimeofday`​/​`clock_gettime` 返回固定值，但会影响正常逻辑，谨慎。

## 0x05 通用 Native 函数打印器

```javascript
function hookExport(modName, funcName, argTypes) {
    var addr = Module.getExportByName(modName, funcName);
    Interceptor.attach(addr, {
        onEnter: function (args) {
            var out = [];
            for (var i = 0; i < argTypes.length; i++) {
                var t = argTypes[i], a = args[i];
                if (t === "str") out.push(a.readUtf8String());
                else if (t === "int") out.push(a.toInt32());
                else if (t === "ptr") out.push(a.toString());
                else out.push(a);
            }
            console.log("[*] " + funcName + "(" + out.join(", ") + ")");
            this.t0 = Date.now();
        },
        onLeave: function (retval) {
            console.log("[*] " + funcName + " -> " + retval + " (" + (Date.now() - this.t0) + "ms)");
        }
    });
}

// 用法
hookExport("libnative.so", "check_flag", ["str", "int"]);
```

## 0x06 dump 解密后的字符串

```javascript
Java.perform(function () {
    var Cls = Java.use("com.example.app.Crypto");
    Cls.decrypt.overload("java.lang.String").implementation = function (s) {
        var r = this.decrypt(s);
        console.log("[decrypt] " + s + " => " + r);
        return r;
    };
});
```

Native 侧在函数返回后 dump 指针：

```javascript
Interceptor.attach(addr, {
    onEnter: function (args) { this.out = args[1]; },
    onLeave: function (retval) {
        try { console.log("[out] " + this.out.readUtf8String()); } catch (e) {}
    }
});
```

## 0x07 hook 构造函数拿上下文

```javascript
Java.perform(function () {
    var Activity = Java.use("com.example.app.MainActivity");
    Activity.onCreate.overload("android.os.Bundle").implementation = function (b) {
        console.log("[*] onCreate, context=" + this);
        this.onCreate(b);
    };
});
```

拿到 ​`this`​ 之后可以接着 ​`this.getApplicationContext()`，很多初始化逻辑都靠它。

## 0x08 RPC：把能力暴露给 Python

```javascript
rpc.exports = {
    listClasses: function (kw) {
        return Java.enumerateLoadedClassesSync().filter(function (c) {
            return c.indexOf(kw) >= 0;
        });
    },
    callCheck: function (s) {
        return Java.use("com.example.app.Check").verify(s);
    }
};
```

```python
import frida, sys

session = frida.get_usb_device().attach("com.example.app")
script = session.create_script(open("hook.js", encoding="utf-8").read())
script.on("message", lambda m, d: print(m))
script.load()

print(script.exports_sync.list_classes("example")[:10])
print(script.exports_sync.call_check("test"))
```

`exports_sync`​ 方法名由 JS 的驼峰自动转下划线：​`listClasses`​ → ​`list_classes`。

## 0x09 一次性检查清单

- 包名/进程名对吗：​`frida-ps -U -a | grep 关键字`
- 架构对吗：​`Process.arch`，32 位 so 不能用 arm64 脚本里的偏移
- 类加载了吗：​`Java.enumerateLoadedClassesSync()` 里 grep 一下
- 方法重载选对了吗：先打 ​`overloads` 的签名
- so 加载了吗：​`Process.enumerateModulesSync()` 里找
- hook 时机对吗：​`-f`​ spawn、​`Java.perform`​、​`setImmediate`​、​`dlopen` 回调

模板的可运行版本在 ​`scripts/hook_template.js`​ 和 ​`scripts/ssl_bypass.js`​，改两行常量就能直接 ​`frida -U -f 包名 -l 脚本.js`。
