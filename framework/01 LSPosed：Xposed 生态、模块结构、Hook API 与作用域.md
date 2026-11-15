---
title: 01 LSPosed：Xposed 生态、模块结构、Hook API 与作用域
date: 2026-11-15T22:53:20+08:00
lastmod: 2026-11-15T22:53:20+08:00
---

# 01 LSPosed：Xposed 生态、模块结构、Hook API 与作用域

# 01 LSPosed：Xposed 生态、模块结构、Hook API 与作用域

LSPosed 是 Xposed API 的现代实现：模块仍然写 ​`IXposedHookLoadPackage`，但注入由 LSPosed 负责（跑在 Zygisk 或 Riru 上）。它把"改 Java 方法"这件事做得足够稳定，是目前 Android Java 层 Hook 的首选。

## 0x00 它和 Xposed 的关系

- 模块代码不用改：还是 ​`de.robv.android.xposed`​ 那套 API（​`XposedBridge`​、​`XposedHelpers`​、​`XC_MethodHook`）。
- 原版 Xposed 改的是 ​`app_process`，LSPosed 通过 Zygisk/Riru 在 zygote 里注入，兼容新 Android。
- 模块是否生效，由 LSPosed 管理器里的**作用域**决定：勾了哪些应用，模块才进哪些进程。

## 0x01 注入链

```text
Magisk (Zygisk)
  └─ zygote 启动时注入 LSPosed 的 zygisk 模块
       └─ 目标 App fork 出来、specialize
            └─ LSPosed 加载 XposedBridge
                 └─ 读模块列表 + 作用域
                      └─ 调用模块的 handleLoadPackage(lpparam)
```

Riru 模式只是把最上面一层换成 Riru，后面的调用链一样。所以排查问题时，先确认 LSPosed 自己是活的（管理器能打开、日志有输出），再看模块。

## 0x02 模块工程结构

```text
app/
├── build.gradle
└── src/main/
    ├── AndroidManifest.xml
    ├── assets/xposed_init
    └── java/com/example/module/HookEntry.java
```

`AndroidManifest.xml` 关键四项：

```xml
<meta-data android:name="xposedmodule" android:value="true" />
<meta-data android:name="xposeddescription" android:value="demo module" />
<meta-data android:name="xposedminversion" android:value="93" />
<meta-data android:name="xposedscope" android:resource="@array/xposed_scope" />
```

`res/values/arrays.xml` 里声明作用域（只是给管理器做默认勾选，最终以管理器里勾的为准）：

```xml
<string-array name="xposed_scope">
    <item>com.example.target</item>
</string-array>
```

`assets/xposed_init` 写入口类的全限定名，一行一个：

```text
com.example.module.HookEntry
```

`build.gradle` 只编译不打包 Xposed API：

```groovy
dependencies {
    compileOnly 'de.robv.android.xposed:api:82'
}
```

> 新版 LSPosed 也支持 libxposed 的新 API，但绝大多数现成模块仍是 82 这套，先学它。

## 0x03 入口与 Hook API

```java
public class HookEntry implements IXposedHookLoadPackage {
    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!"com.example.target".equals(lpparam.packageName)) return;

        XposedHelpers.findAndHookMethod(
            "com.example.target.Check",       // 类名
            lpparam.classLoader,              // 必须用目标的 ClassLoader
            "verify",                         // 方法名
            String.class,                     // 参数类型
            new XC_MethodHook() {
                @Override
                protected void beforeHookedMethod(MethodHookParam param) {
                    Log.i("demo", "verify(" + param.args[0] + ")");
                }

                @Override
                protected void afterHookedMethod(MethodHookParam param) {
                    param.setResult(true);    // 改返回值
                }
            }
        );
    }
}
```

常用 API：

|API|用途|
| -------------| ----------------------------|
|`findAndHookMethod`|精确匹配一个方法（含重载）|
|`findAndHookConstructor`|构造函数|
|`hookAllMethods`|同名方法全部挂上|
|`hookAllConstructors`|所有构造|
|`XposedHelpers.getObjectField`​ / ​`setObjectField`|读写字段|
|`XposedHelpers.callMethod`​ / ​`callStaticMethod`|主动调用|
|`XposedBridge.log`|写 LSPosed 日志|

改参数的写法（参数是值拷贝，改 ​`param.args[i]`​ 在 ​`before` 里对引用类型有效）：

```java
@Override
protected void beforeHookedMethod(MethodHookParam param) {
    param.args[1] = "替换后的参数";
}
```

改返回值用 ​`param.setResult(...)`​；想完全接管方法体，覆写 ​`beforeHookedMethod`​ 后 ​`setResult`​ 并 return，或者用 ​`XC_MethodReplacement`。

## 0x04 ClassLoader 与作用域

- `lpparam.classLoader`​ 是目标应用的 loader，​`findAndHookMethod` 的类名必须能用它加载到。
- 加固/多 dex 场景，类可能不在默认 loader 里：用 ​`lpparam.classLoader.loadClass(...)`​ 探一下，或 hook ​`ClassLoader.loadClass` 找实际 loader。
- 作用域没勾：​`handleLoadPackage` 根本不会被调用。先确认管理器里勾了目标应用。

## 0x05 资源 Hook

想改字符串、颜色、布局，用 ​`IXposedHookInitPackageResources`：

```java
public class ResHook implements IXposedHookInitPackageResources {
    @Override
    public void handleInitPackageResources(XC_InitPackageResources.InitPackageResourcesParam resparam) {
        if (!"com.example.target".equals(resparam.packageName)) return;
        resparam.res.setReplacement("com.example.target", "string", "app_name", "改过的名字");
    }
}
```

`xposed_init` 里可以写多行，把 HookEntry 和 ResHook 都列上。

## 0x06 调试

```bash
# 模块日志（XposedBridge.log 的输出）
adb logcat -s LSPosed

# 崩溃与 ART 日志
adb logcat | grep -iE "AndroidRuntime|LSPosed|Xposed"

# 确认模块被加载
adb shell su -c "ls /data/adb/lspd/log"
```

排查顺序：

1. LSPosed 管理器里模块是否启用、作用域是否勾选。
2. `handleLoadPackage` 有没有打印（日志里能看到包名）。
3. 类名/方法签名对不对（用 ​`javap` 或 jadx 核对，注意重载）。
4. 目标方法是否被内联/R8 优化（见坑点）。

## 0x07 常见坑

- **方法被 ART 内联**：短方法可能被内联，Hook 不到。解法是 hook 调用方，或让模块在 ​`handleLoadPackage` 里更早挂上。
- **重载匹配错**：​`findAndHookMethod`​ 参数类型必须和声明完全一致，​`int`​ 与 ​`Integer` 不同。
- **类被 R8 混淆**：名字变了，先 ​`enumerateLoadedClasses` 或 jadx 确认实际类名。
- **加固/双进程**：目标可能在 ​`:remote`​ 进程里，作用域要覆盖子进程，或按 ​`processName` 判断。
- **Android 高版本隐藏 API 限制**：反射受限时用 ​`XposedHelpers`​ 提供的封装，别直接 ​`Class.forName`。
- **模块与目标 ABI 不一致**：模块本身是纯 Java 一般没事；带 native 的模块要提供对应 ABI。
- **改返回值导致逻辑异常**：只改 ​`afterHookedMethod`​ 里的 ​`setResult`​，不要在 ​`before` 里 return 而不调用原方法，除非你确认副作用可接受。
