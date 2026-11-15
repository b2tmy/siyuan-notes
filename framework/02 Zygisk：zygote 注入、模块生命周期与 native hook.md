---
title: 02 Zygisk：zygote 注入、模块生命周期与 native hook
date: 2026-11-15T22:53:21+08:00
lastmod: 2026-11-15T22:53:21+08:00
---

# 02 Zygisk：zygote 注入、模块生命周期与 native hook

# 02 Zygisk：zygote 注入、模块生命周期与 native hook

Zygisk 是 Magisk 24 起内置的注入框架：模块是一个 native ​`.so`，在 zygote fork 出应用进程、执行 specialize 的阶段被加载，因此比普通 Xposed 模块更早、更底层，能直接改 native 世界的东西。LSPosed 的 Zygisk 模式就架在它上面。

## 0x00 它解决什么问题

- 应用进程还没开始跑 Java 代码时就能介入（​`preAppSpecialize`）。
- 可以拿到包名、uid、ABI，按进程决定加不加载。
- 能直接 hook native：PLT/GOT、inline hook、JNI 函数。
- 不依赖 Xposed API，纯 C/C++ 模块也能用。

代价是：没有 Java 层那种"按类名改方法"的便利，所有事情要自己做；写错一个类型/ABI 就直接崩 zygote 或目标进程。

## 0x01 注入链与时序

```text
magiskd
  └─ 启动时把 zygisk 注入 zygote（zygote 进程里多出 zygisk 的 .so）
       └─ zygote fork 出 app 进程
            ├─ preAppSpecialize(args)    ← 此时还没跑 App 代码，能拿到包名/uid
            ├─ specialize（确定 classpath、ABI、seccomp 等）
            └─ postAppSpecialize(args)   ← App 代码即将/已经开始跑
```

- `preServerSpecialize`​ / ​`postServerSpecialize`​ 对应 ​`system_server`。
- 模块在 ​`onLoad`​ 里拿到 ​`Api*`​ 和 ​`JNIEnv*`，之后的生命周期回调都用它。
- 想"只对某个包生效"，就在 ​`preAppSpecialize`​ 里读 ​`nice_name`，不匹配直接返回，模块不会进那个进程。

## 0x02 模块目录

```text
/data/adb/modules/<模块 id>/
├── module.prop
└── zygisk/
    ├── arm64-v8a.so
    ├── armeabi-v7a.so
    ├── x86_64.so
    └── x86.so
```

`module.prop`：

```properties
id=demozygisk
name=Demo Zygisk Module
version=v1.0
versionCode=1
author=you
description=最小 Zygisk 模块
```

注意：

- 目录里的 ​`.so`​ 文件名必须是 ABI 名，不是 ​`libxxx.so`。
- 只放设备实际需要的 ABI，少一个架构在该设备上就是不生效。
- 改完模块后 ​`su -c "magisk --zygisk"` 查看状态，或重启 zygote（重启手机最稳）。

## 0x03 生命周期与 API

```cpp
class ModuleBase {
public:
    virtual void onLoad(Api *api, JNIEnv *env) {}
    virtual void preAppSpecialize(AppSpecializeArgs *args) {}
    virtual void postAppSpecialize(const AppSpecializeArgs *args) {}
    virtual void preServerSpecialize(ServerSpecializeArgs *args) {}
    virtual void postServerSpecialize(const ServerSpecializeArgs *args) {}
};
```

`AppSpecializeArgs` 里常用的字段（都是指针，取值前判空）：

|字段|含义|
| -------------| --------------------|
|`nice_name`|进程名，通常是包名|
|`uid`​ / ​`gid`|进程 uid/gid|
|`gids`|附加组|
|`runtime_flags`|运行时标志|
|`instruction_set`|目标 ABI|
|`app_data_dir`|应用数据目录|

`Api`​ 提供的能力（不同 Magisk 版本函数略有增减，以你使用的 ​`zygisk.hpp` 为准）：

- `connectCompanion()`：连到 zygiskd 的 companion 进程，做跨进程通信。
- `getModuleDir()`：拿到模块自己的目录 fd。
- `pltHookRegister()`​ / ​`pltHookCommit()`：注册并提交 PLT hook（较新版本提供）。
- `exemptFd()`：让某个 fd 不被 zygisk 的 fd 清理逻辑影响。

## 0x04 最小模块

```cpp
#include <jni.h>
#include <android/log.h>
#include <zygisk.hpp>

#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, "demozygisk", __VA_ARGS__)

using zygisk::Api;
using zygisk::AppSpecializeArgs;
using zygisk::ServerSpecializeArgs;

class DemoModule : public zygisk::ModuleBase {
public:
    void onLoad(Api *api, JNIEnv *env) override {
        this->api = api;
        this->env = env;
    }

    void preAppSpecialize(AppSpecializeArgs *args) override {
        const char *name = env->GetStringUTFChars(args->nice_name, nullptr);
        LOGI("preAppSpecialize: %s", name);
        env->ReleaseStringUTFChars(args->nice_name, name);
    }

    void postAppSpecialize(const AppSpecializeArgs *args) override {
        LOGI("postAppSpecialize");
    }

    void preServerSpecialize(ServerSpecializeArgs *args) override {
        LOGI("system_server");
    }

private:
    Api *api = nullptr;
    JNIEnv *env = nullptr;
};

REGISTER_ZYGISK_MODULE(DemoModule)
```

`REGISTER_ZYGISK_MODULE`​ 负责导出入口符号，模块被 dlopen 后由 zygisk 调用 ​`onLoad`。

## 0x05 编译

需要 NDK 和对应 Magisk 版本的 ​`zygisk.hpp`​（在 Magisk 源码的 ​`native/src/include/` 下）。

`CMakeLists.txt`：

```cmake
cmake_minimum_required(VERSION 3.18)
project(demozygisk CXX)

add_library(demozygisk SHARED module.cpp)
target_compile_features(demozygisk PRIVATE cxx_std_17)
target_include_directories(demozygisk PRIVATE ${ZYGISK_INCLUDE})
target_link_libraries(demozygisk PRIVATE log)

set_target_properties(demozygisk PROPERTIES PREFIX "")
```

```bash
cmake -B build -DCMAKE_TOOLCHAIN_FILE=$NDK/build/cmake/android.toolchain.cmake \
      -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-29 \
      -DZYGISK_INCLUDE=/path/to/magisk/native/src/include
cmake --build build
```

输出 ​`demozygisk.so`​，改名成 ​`arm64-v8a.so`​ 放进模块目录的 ​`zygisk/` 下。

## 0x06 在 Zygisk 里做 native hook

三种常见做法，按侵入程度排：

1. **PLT/GOT hook**：用 ​`Api::pltHookRegister`​ + ​`pltHookCommit`​ 挂导入函数（如 ​`open`​、​`strstr`）。只影响当前进程的调用点，最安全。
2. **inline hook**：用 Dobby / ShadowHook / bhook 改函数头。能挂任意函数，包括没走 PLT 的内部调用，风险也最高。
3. **JNI 层**：​`postAppSpecialize`​ 里拿到 ​`JavaVM`​/​`JNIEnv`​，用 ​`RegisterNatives` 改注册表，或反射改 Java 方法（相当于自己做一套 LSPosed）。

inline hook 的骨架：

```cpp
#include <dobby.h>

static int (*orig_strcmp)(const char *, const char *) = nullptr;

int fake_strcmp(const char *a, const char *b) {
    LOGI("strcmp(%s, %s)", a, b);
    return orig_strcmp(a, b);
}

// 在 postAppSpecialize 里
DobbyHook((void *)strcmp, (void *)fake_strcmp, (void **)&orig_strcmp);
```

## 0x07 companion 进程

需要在 zygote 上下文之外做事（读文件、连 socket、解大资源）时用 companion：

```cpp
// 模块侧
int fd = api->connectCompanion();
write(fd, &cmd, sizeof(cmd));

// companion 侧
static void companion_entry(int fd) {
    // 这里运行在 zygiskd fork 出来的独立进程
}
REGISTER_ZYGISK_COMPANION(companion_entry)
```

companion 进程没有目标应用的 JNIEnv，适合做纯 native 的辅助工作。

## 0x08 调试

```bash
# 模块自己的日志
adb logcat -s demozygisk

# zygisk / magisk 状态
adb shell su -c "magisk --zygisk"
adb logcat | grep -iE "zygisk|magisk"

# 确认模块目录与 so
adb shell su -c "ls -l /data/adb/modules/demozygisk/zygisk"
```

排查顺序：

1. Magisk 设置里 Zygisk 是否开启。
2. `module.prop` 的 id 与目录名是否一致。
3. `.so`​ 是否放在 ​`zygisk/<abi>.so`，架构是否匹配。
4. 日志里有没有 ​`onLoad`​ / ​`preAppSpecialize`。
5. 崩溃就看 tombstone：​`adb shell su -c "ls /data/tombstones"`。

## 0x09 常见坑

- **ABI 写错**：​`arm64-v8a.so` 里放 32 位库，加载直接失败。
- **API 版本不匹配**：用新头文件编译却跑在旧 Magisk 上，符号找不到。
- **在 preAppSpecialize 里做重活**：此时还在 zygote 的上下文，阻塞会影响整个启动；重活放 ​`post`。
- **忘记释放 JNI 字符串**：​`GetStringUTFChars`​ 必须配 ​`ReleaseStringUTFChars`，否则泄漏/崩溃。
- **DenyList / 隐藏生效**：目标在 DenyList 里时 Zygisk 默认不注入，需要模块自己处理或调整策略。
- **写文件路径**：zygote 上下文权限有限，落盘走 companion 或 ​`getModuleDir()`。
- **system_server 崩溃**：​`preServerSpecialize` 写错会导致系统起不来，先在普通应用上验证。
