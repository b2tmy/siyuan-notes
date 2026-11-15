---
title: 04 最小可运行模块：LSPosed 与 Zygisk 各一套骨架
date: 2026-11-15T22:53:21+08:00
lastmod: 2026-11-15T22:53:21+08:00
---

# 04 最小可运行模块：LSPosed 与 Zygisk 各一套骨架

# 04 最小可运行模块：LSPosed 与 Zygisk 各一套骨架

这一篇是可以直接抄的工程骨架。目标不是功能多，而是**先让它跑起来、日志能出来**，再往里加逻辑。

## 0x00 LSPosed 模块（Java）

### 目录

```text
lsposed-demo/
├── build.gradle
├── settings.gradle
└── app/
    ├── build.gradle
    └── src/main/
        ├── AndroidManifest.xml
        ├── assets/xposed_init
        ├── res/values/arrays.xml
        └── java/com/example/demo/HookEntry.java
```

### app/build.gradle

```groovy
plugins { id 'com.android.application' }

android {
    namespace 'com.example.demo'
    compileSdk 34

    defaultConfig {
        applicationId "com.example.demo"
        minSdk 29
        targetSdk 34
        versionCode 1
        versionName "1.0"
    }
}

dependencies {
    compileOnly 'de.robv.android.xposed:api:82'
}
```

### AndroidManifest.xml

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application android:label="Demo Module">
        <meta-data android:name="xposedmodule" android:value="true" />
        <meta-data android:name="xposeddescription" android:value="demo hook" />
        <meta-data android:name="xposedminversion" android:value="93" />
        <meta-data android:name="xposedscope" android:resource="@array/xposed_scope" />
    </application>
</manifest>
```

### res/values/arrays.xml

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string-array name="xposed_scope">
        <item>com.example.target</item>
    </string-array>
</resources>
```

### assets/xposed_init

```text
com.example.demo.HookEntry
```

### HookEntry.java

```java
package com.example.demo;

import android.util.Log;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

public class HookEntry implements IXposedHookLoadPackage {
    private static final String TAG = "demo-lsposed";

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) {
        XposedBridge.log(TAG + " loaded in " + lpparam.packageName);
        if (!"com.example.target".equals(lpparam.packageName)) return;

        try {
            XposedHelpers.findAndHookMethod(
                "com.example.target.Check",
                lpparam.classLoader,
                "verify",
                String.class,
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        Log.i(TAG, "verify(" + param.args[0] + ")");
                    }

                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        param.setResult(true);
                    }
                }
            );
        } catch (Throwable t) {
            XposedBridge.log(TAG + " hook failed: " + t);
        }
    }
}
```

### 安装与验证

```bash
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
# LSPosed 管理器里启用模块、勾选目标应用，然后重启目标进程
adb shell am force-stop com.example.target
adb logcat -s LSPosed demo-lsposed
```

## 0x01 Zygisk 模块（C++）

### 目录

```text
zygisk-demo/
├── module.prop
├── CMakeLists.txt
├── module.cpp
└── build.sh
```

### module.prop

```properties
id=demozygisk
name=Demo Zygisk Module
version=v1.0
versionCode=1
author=you
description=最小 Zygisk 模块
```

### module.cpp

```cpp
#include <jni.h>
#include <unistd.h>
#include <android/log.h>
#include <zygisk.hpp>

#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, "demozygisk", __VA_ARGS__)

using zygisk::Api;
using zygisk::AppSpecializeArgs;
using zygisk::ServerSpecializeArgs;

class DemoModule : public zygisk::ModuleBase {
public:
    void onLoad(Api *api, JNIEnv *env) override {
        api_ = api;
        env_ = env;
        LOGI("onLoad");
    }

    void preAppSpecialize(AppSpecializeArgs *args) override {
        if (!args->nice_name) return;
        const char *name = env_->GetStringUTFChars(args->nice_name, nullptr);
        if (name) {
            LOGI("preAppSpecialize: %s", name);
            env_->ReleaseStringUTFChars(args->nice_name, name);
        }
    }

    void postAppSpecialize(const AppSpecializeArgs *args) override {
        LOGI("postAppSpecialize");
    }

    void preServerSpecialize(ServerSpecializeArgs *args) override {
        LOGI("preServerSpecialize");
    }

private:
    Api *api_ = nullptr;
    JNIEnv *env_ = nullptr;
};

REGISTER_ZYGISK_MODULE(DemoModule)
```

### CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.18)
project(demozygisk CXX)

add_library(demozygisk SHARED module.cpp)
target_compile_features(demozygisk PRIVATE cxx_std_17)
target_include_directories(demozygisk PRIVATE ${ZYGISK_INCLUDE})
target_link_libraries(demozygisk PRIVATE log)

set_target_properties(demozygisk PROPERTIES PREFIX "")
```

### build.sh

```bash
#!/usr/bin/env bash
set -e
: "${NDK:?set NDK to your ndk path}"
: "${ZYGISK_INCLUDE:?set ZYGISK_INCLUDE to magisk native/src/include}"

for abi in arm64-v8a armeabi-v7a x86_64 x86; do
  cmake -B "build/$abi" \
    -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI="$abi" -DANDROID_PLATFORM=android-29 \
    -DZYGISK_INCLUDE="$ZYGISK_INCLUDE"
  cmake --build "build/$abi" -j
  mkdir -p "out/zygisk"
  cp "build/$abi/demozygisk.so" "out/zygisk/$abi.so"
done
cp module.prop out/
```

### 安装

```bash
# 打包
cd out && zip -r ../demozygisk.zip . && cd ..

# 设备上
adb push demozygisk.zip /data/local/tmp/
adb shell su -c "magisk --install-module /data/local/tmp/demozygisk.zip"
adb reboot

# 验证
adb logcat -s demozygisk
adb shell su -c "ls -l /data/adb/modules/demozygisk/zygisk"
```

KernelSU / APatch 用户把 ​`magisk --install-module` 换成对应的模块安装方式，并确认已装 ZygiskNext。

## 0x02 从骨架到功能

1. 先只打日志，确认 ​`handleLoadPackage`​ / ​`preAppSpecialize` 被调用。
2. LSPosed 侧：打印目标方法签名，再改返回值。
3. Zygisk 侧：先在 ​`postAppSpecialize`​ 里做一次 ​`dlopen`​/​`dlsym` 验证能拿到目标 so。
4. 再做 PLT hook 或 inline hook，一次只加一个点。
5. 每次改动都 ​`am force-stop` 目标进程，不要指望热更新。

## 0x03 调试速查

```bash
adb logcat -s LSPosed
adb logcat -s demozygisk
adb shell su -c "magisk --zygisk"
adb shell am force-stop com.example.target
adb shell su -c "ls /data/tombstones"
```
