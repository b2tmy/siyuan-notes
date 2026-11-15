---
title: 02 Java 层：perform、use、overload、implementation
date: 2026-11-15T21:36:31+08:00
lastmod: 2026-11-15T21:36:31+08:00
---

# 02 Java 层：perform、use、overload、implementation

# 02 Java 层：perform、use、overload、implementation

Java 层的三板斧：​`Java.perform`​ 保证在 ART 里执行，​`Java.use`​ 拿到类包装，​`overload().implementation`​ 替换方法体。记住顺序：先 ​`Java.perform`​，再 ​`Java.use`，最后才是 hook。

## 0x00 基本骨架

```javascript
Java.perform(function () {
    console.log("android " + Java.androidVersion);

    var Cls = Java.use("com.example.app.Check");
    console.log(Cls);                       // 打印类包装，确认找到了

    Cls.verify.implementation = function (a, b) {
        console.log("verify called:", a, b);
        var ret = this.verify(a, b);        // 调原逻辑
        console.log("verify ret:", ret);
        return ret;
    };
});
```

- `Java.perform`​ 是异步排进 ART 的队列；​`Java.performNow` 是当前线程立刻执行（必须在已 attach 的线程里用）。
- `Java.available` 为 false 说明不是 Android 进程或 frida 没注入成功。
- 脚本在 ​`frida -f`​ 的极早期执行时，​`Java.perform`​ 可能要等 ​`setImmediate` 或延后几百毫秒，见 05。

## 0x01 Java.use 与构造

```javascript
var Cls = Java.use("com.example.app.User");

var u = Cls.$new();                 // 无参构造
var u2 = Cls.$new("name", 18);      // 有参构造，按参数个数自动匹配
var u3 = Cls.$new.overload("java.lang.String").call(Cls, "name");  // 指定重载

// hook 构造函数
Cls.$init.overload("java.lang.String", "int").implementation = function (name, age) {
    console.log("new User:", name, age);
    this.$init(name, age);
};
```

- `$new`​ 找不到匹配重载会抛 ​`Error: <init>(): argument types do not match`​，用 ​`$init.overloads` 先看签名。
- `$init`​ 内部调用原构造用 ​`this.$init(...)`​，别用 ​`Cls.$init.call`。
- `$dispose()` 释放本地引用，长时间循环里建议加，避免 ART 引用表涨。

## 0x02 overload：重载是第一个坎

```javascript
var Cls = Java.use("com.example.app.Check");

// 列出所有重载签名
Cls.verify.overloads.forEach(function (o) {
    console.log(o.argumentTypes.map(t => t.className).join(", "));
});

// 精确匹配
Cls.verify.overload("java.lang.String", "int").implementation = function (s, n) {
    console.log(s, n);
    return this.verify(s, n);
};

// 无参
Cls.verify.overload().implementation = function () {
    return true;
};
```

类型名写法：基本类型用 ​`int`​ ​`long`​ ​`boolean`​ ​`byte[]`​；对象用全限定名 ​`java.lang.String`​、​`android.content.Context`​；数组 ​`[B`​ 或 ​`byte[]`​ 均可，推荐 ​`byte[]`。

## 0x03 改返回值、改参数

```javascript
var Cls = Java.use("com.example.app.Check");

// 只改返回值：先存原方法，避免递归
var orig = Cls.verify.overload("java.lang.String");
orig.implementation = function (s) {
    var r = orig.call(this, s);        // 调原实现
    console.log("orig:", r);
    return true;                        // 直接给 true
};
```

参数是值传递，**不能原地改**。要改参数，就在 hook 里用新值调原方法：

```javascript
var orig = Cls.login.overload("java.lang.String", "java.lang.String");
orig.implementation = function (user, pass) {
    console.log("login:", user, pass);
    return orig.call(this, user, "改写后的密码");
};
```

静态方法用 ​`Cls.method.call(Cls, ...)`​，​`this` 传类本身：

```javascript
var origStatic = Cls.isVip.overload();
origStatic.implementation = function () {
    return true;
};
```

## 0x04 字段读写

```javascript
var Cls = Java.use("com.example.app.User");
var inst = Cls.$new();

console.log(inst.name.value);        // 实例字段
inst.name.value = "hacked";

console.log(Cls.sCount.value);       // 静态字段
Cls.sCount.value = 999;
```

## 0x05 枚举与查找实例

```javascript
Java.perform(function () {
    // 所有已加载类
    Java.enumerateLoadedClassesSync()
        .filter(c => c.indexOf("com.example") >= 0)
        .forEach(c => console.log(c));

    // 遍历存活实例（会触发 GC 遍历，实例多时慢）
    Java.choose("com.example.app.User", {
        onMatch: function (inst) {
            console.log("found:", inst, inst.name.value);
        },
        onComplete: function () {}
    });
});
```

`onMatch`​ 里不要做重活，也不要长时间持有实例；需要留存就 ​`Java.retain(inst)`。

## 0x06 ClassLoader：找不到类先看这里

加固或动态加载的 App，​`Java.use`​ 会报 ​`ClassNotFoundException`，因为默认 loader 是系统的。逐个试：

```javascript
Java.perform(function () {
    Java.enumerateClassLoadersSync().forEach(function (loader) {
        try {
            if (loader.findClass("com.example.app.Check")) {
                console.log("hit loader:", loader);
                Java.classFactory.loader = loader;   // 切换默认 loader
            }
        } catch (e) {}
    });

    var Cls = Java.use("com.example.app.Check");     // 切换后再 use
    console.log(Cls);
});
```

也可以直接指定：​`Java.use("com.example.app.Check", loader)`（部分版本支持）。

## 0x07 类型转换与数组

```javascript
var Str = Java.use("java.lang.String");
var obj = Cls.getSomething();          // 返回 Object

var s = Java.cast(obj, Str);           // 强转，失败会抛异常
console.log(s.toString());

var bytes = Java.array("byte", [0x41, 0x42, 0x43]);
var ints = Java.array("int", [1, 2, 3]);
console.log(bytes.length);

// Java byte[] 转 JS 字符串
function jbytesToString(arr) {
    var s = "";
    for (var i = 0; i < arr.length; i++) s += String.fromCharCode(arr[i] & 0xff);
    return s;
}
```

## 0x08 打印调用栈

```javascript
function stack() {
    var Log = Java.use("android.util.Log");
    var Exception = Java.use("java.lang.Exception");
    return Log.getStackTraceString(Exception.$new());
}

Java.use("com.example.app.Check").verify.implementation = function (s) {
    console.log(stack());
    return this.verify(s);
};
```

## 0x09 动态注册一个类（补环境用）

```javascript
var Listener = Java.registerClass({
    name: "com.example.FakeListener",
    implements: [Java.use("com.example.app.Callback")],
    methods: {
        onResult: function (code) {
            console.log("onResult:", code);
        }
    }
});
```

`Java.registerClass`​ 的接口方法必须全部实现，否则加载时抛 ​`AbstractMethodError`。

## 0x0a 在主线程序列执行

```javascript
Java.scheduleOnMainThread(function () {
    // 需要 Looper 的操作放这里
});
```

不改 UI 一般用不上；但调用某些必须主线程的 API（Toast、View）时必须包一层。
