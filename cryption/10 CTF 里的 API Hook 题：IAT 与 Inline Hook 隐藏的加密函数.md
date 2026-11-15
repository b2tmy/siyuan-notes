---
title: 10 CTF 里的 API Hook 题：IAT 与 Inline Hook 隐藏的加密函数
date: 2026-11-15T22:05:43+08:00
lastmod: 2026-11-15T22:10:31+08:00
---

# 10 CTF 里的 API Hook 题：IAT 与 Inline Hook 隐藏的加密函数

# 07 CTF 里的 API Hook 题：IAT / Inline Hook 与隐藏加密函数

这类题的特征很明确：程序跑起来之后，把系统 DLL 里某个函数的权限改成可写（VirtualProtect / mprotect），在函数开头塞一条跳转，或者直接改导入表项，把 ​`memcmp`​、​`strcmp`​、​`GetProcAddress`​、​`Sleep` 这类自带函数接到自己的实现上——真正的加密、校验、解密逻辑就藏在那条跳转的目标里，磁盘文件里根本没有这段代码。你要做两件事：找到 hook 的痕迹，把隐藏函数从内存里挖出来。

> 原则：hook 一定留痕。改 IAT 有表项异常，改函数头有 ​`E9`​ / ​`FF 25`​，改权限有 ​`VirtualProtect` 调用点，改内存有 RWX 段。先找痕迹，再谈 dump；上来就硬逆主函数通常是在浪费时间。

## 0x00 先判断是不是这类题

看到下面任意两三条，基本可以按 API hook 题处理：

- 导入表里有 ​`memcmp`​ / ​`strcmp`​ / ​`IsDebuggerPresent`，但交叉引用很少，或者调用点直接跳到别处。
- 函数开头 5 字节是 ​`E9`​（jmp rel32）、​`FF 25`​（jmp qword ptr [rip+…]），或者 ​`48 B8 … FF E0`（mov rax, imm64; jmp rax）。
- 节区权限异常：​`.text`​ 变成 RWX，或者出现 ​`PAGE_EXECUTE_READWRITE`​ 常量 ​`0x40`。
- 字符串里有 ​`VirtualProtect`​、​`VirtualAlloc`​、​`FlushInstructionCache`​、​`mprotect`。
- 程序加载了 exe 同目录下的同名 DLL（DLL 劫持 / 侧加载）。
- 主逻辑很短，校验结果来自一个"不在任何模块里"的地址。

## 0x01 四种 hook 与"权限"的关系

|类型|改的是|必须先拿到的权限|静态痕迹|
| -------------------------| ------------------------| -----------------------------| ----------------------|
|IAT Hook|导入地址表里的函数指针|写 ​`.rdata`​ / ​`.data`​，通常要 ​`VirtualProtect`|表项指向模块外地址|
|EAT / DLL 劫持|导出表或加载顺序|文件系统写权限|exe 目录有同名 DLL|
|Inline Hook|目标函数开头若干字节|代码段可写，​`VirtualProtect` 改 RWX|函数头 ​`E9`​ / ​`FF 25`|
|GOT / PLT Hook（Linux）|`.got.plt` 表项|`mprotect` 改页属性|表项指向非 libc 地址|

题目说的"改了系统函数权限再 hook 进去"，九成是 **Inline Hook + VirtualProtect**：先在 kernel32/ntdll 的函数头上写 jmp，跳到自己准备的隐藏函数。这类 hook 是全局的，一旦挂上，整个进程调用这个 API 都会进隐藏函数。

## 0x02 静态定位：先看导入表和函数头

### 看 IAT 是否被改

```python
#!/usr/bin/env python3
"""列出 PE 导入表，标出指向非系统模块的 IAT 项。"""
import pefile

pe = pefile.PE("challenge.exe", fast_load=True)
pe.parse_data_directories()

for entry in pe.DIRECTORY_ENTRY_IMPORT:
    dll = entry.dll.decode()
    print(f"[{dll}]")
    for imp in entry.imports:
        addr = imp.address
        print(f"  {imp.name.decode() if imp.name else hex(imp.ordinal):<24} "
              f"iat=0x{addr:08x} hint=0x{imp.hint or 0:04x}")
```

运行期被改过的项，在内存里会指向堆或私有内存（地址不在任何模块区间）。对比磁盘文件与内存镜像的 IAT 是最快的判断方式：

```text
x64dbg: 视图 → 内存布局 → 找 exe 的 .rdata → 对比文件偏移
```

### 看函数头

```python
from capstone import *

CODE = open("dumped.bin", "rb").read()
BASE = 0x140001000

md = Cs(CS_ARCH_X86, CS_MODE_64)
for insn in md.disasm(CODE, BASE):
    if insn.mnemonic == "jmp":
        print(hex(insn.address), insn.mnemonic, insn.op_str)
    if insn.address - BASE > 0x200:
        break
```

典型的 hook 头：

```asm
; 5 字节相对跳转
E9 xx xx xx xx          jmp target

; 间接跳转（x64 常用，不占 rel32 范围限制）
FF 25 00 00 00 00       jmp qword ptr [rip+0]
xx xx xx xx xx xx xx xx ; 目标地址

; mov rax, imm64; jmp rax
48 B8 xx xx xx xx xx xx xx xx
FF E0
```

热补丁（hotpatch）会先改函数前面的 5 个填充字节，再把入口改成 ​`jmp short`​，看到 ​`mov edi, edi`​ 后面跟 ​`E9` 也要怀疑。

## 0x03 动态定位：拦权限修改，抓写入点

权限被改的那一刻，就是隐藏代码被写进去的时刻。优先 hook 这三个 API：

```javascript
// Frida（Windows 目标进程）
function hookExport(dll, name, onEnter, onLeave) {
    var addr = Module.getExportByName(dll, name);
    Interceptor.attach(addr, { onEnter: onEnter, onLeave: onLeave });
}

hookExport("kernel32.dll", "VirtualProtect", function (args) {
    var addr = args[0];
    var size = args[1].toInt32();
    var prot = args[2].toInt32();
    console.log(`[VP] addr=${addr} size=0x${size.toString(16)} prot=0x${prot.toString(16)}`);
    if (prot & 0x40) {                      // PAGE_EXECUTE_READWRITE
        this.target = addr;
        this.size = size;
        console.log(hexdump(addr, { length: Math.min(size, 64) }));
    }
}, function () {
    if (this.target) {
        console.log("[VP] after:");
        console.log(hexdump(this.target, { length: Math.min(this.size, 64) }));
        this.target = null;
    }
});

hookExport("kernel32.dll", "VirtualAlloc", function (args) {
    console.log(`[VA] size=0x${args[1].toInt32().toString(16)} prot=0x${args[2].toInt32().toString(16)}`);
});

hookExport("kernel32.dll", "FlushInstructionCache", function (args) {
    console.log(`[FIC] base=${args[1]} size=0x${args[2].toInt32().toString(16)}`);
});

hookExport("kernel32.dll", "GetProcAddress", function (args) {
    var name = args[1];
    try { console.log("[GPA] " + name.readCString()); } catch (e) {}
});
```

x64dbg 对应命令（x64 调用约定：rcx, rdx, r8, r9）：

```text
bp VirtualProtect
log "VP addr={p:rcx} size={p:rdx} prot={p:r8}"
```

在 ​`VirtualProtect`​ 返回处下断，直接 ​`dump rcx` 看这块内存变成了什么。

## 0x04 把隐藏加密函数挖出来

### 方法一：RWX 区域扫函数序言

```javascript
Process.enumerateRanges("rwx").forEach(function (r) {
    console.log(`[rwx] ${r.base} size=0x${r.size.toString(16)}`);
    try {
        var m = Memory.scanSync(r.base, Math.min(r.size, 0x20000), "55 48 89 E5");
        m.forEach(function (hit) { console.log("  candidate func: " + hit.address); });
    } catch (e) {}
});
```

ARM 是 ​`F0 4F 2D E9`（push {r4-r11, lr}）之类，按目标架构换特征。

### 方法二：对比磁盘与内存

隐藏函数通常只存在于内存（运行期解密 + 写入）。做法是拿到进程内存里该模块的镜像，和磁盘文件按节对齐比对，差异区域就是被 patch / 解密出来的代码：

```text
1. x64dbg 附加 → 内存布局 → 选中 exe/so → 右键 dump 到文件
2. 用 pefile 按 SectionAlignment 对齐后与磁盘文件做 diff
3. 差异区反汇编，找 call/jmp 目标
```

工具上：​`pe-sieve`​、​`Process Hacker`​ 的模块 dump、​`Scylla` 的修复导入表都能直接用。

### 方法三：从系统函数入口顺藤摸瓜

已知 ​`memcmp` 被 hook 时，直接读它的入口字节：

```javascript
var p = Module.getExportByName("msvcrt.dll", "memcmp");
console.log(hexdump(p, { length: 32 }));
// E9 开头 → 读 rel32 算目标
var rel = p.add(1).readS32();
console.log("hook target = " + p.add(5).add(rel));
```

拿到目标地址后：

```javascript
var target = p.add(5).add(rel);
console.log(hexdump(target, { length: 64 }));
Interceptor.attach(target, {
    onEnter: function (args) {
        console.log("[hidden] arg0=" + args[0].readUtf8String());
        console.log("[hidden] arg1=" + args[1].readUtf8String());
    },
    onLeave: function (ret) {
        console.log("[hidden] ret=" + ret.toInt32());
    }
});
```

这一步就已经能拿到明文了：隐藏函数通常就是"比较 + 解密"的实体，参数里直接有输入的 flag 和解密后的目标串。

## 0x05 恢复原函数（题目要求"绕过 hook"时）

### 还原 IAT 项

```c
#include <windows.h>

void restore_iat(void **iat_entry, void *real_func) {
    DWORD old;
    VirtualProtect(iat_entry, sizeof(void *), PAGE_READWRITE, &old);
    *iat_entry = real_func;
    VirtualProtect(iat_entry, sizeof(void *), old, &old);
    FlushInstructionCache(GetCurrentProcess(), iat_entry, sizeof(void *));
}
```

`real_func`​ 从原始 DLL 的导出表拿：​`GetProcAddress(LoadLibraryA("msvcrt.dll"), "memcmp")`——注意要在 hook 生效前就拿到，或者从磁盘重新加载一份。

### 去掉 inline hook

```c
void unhook_inline(void *target, const unsigned char *original, size_t len) {
    DWORD old;
    VirtualProtect(target, len, PAGE_EXECUTE_READWRITE, &old);
    memcpy(target, original, len);
    VirtualProtect(target, len, old, &old);
    FlushInstructionCache(GetCurrentProcess(), target, len);
}
```

原始字节从磁盘上的 DLL 文件里抠：按函数 RVA 定位文件偏移，读前 16 字节。

### 反调试类 hook

`IsDebuggerPresent`​、​`NtQueryInformationProcess`​、​`CheckRemoteDebuggerPresent` 被改过时，最省事的是用 ScyllaHide / TitanHide 插件直接隐藏调试器；要在脚本里做，就 hook 这些函数返回原始值（0 / 0xFFFFFFFF）。

## 0x06 自己写 hook 去插桩（MinHook 版）

拿到隐藏函数地址后，除了 Frida，也可以编译一个小 DLL 注入进去，用 MinHook 挂：

```c
#include <windows.h>
#include "MinHook.h"

typedef int (WINAPI *memcmp_t)(const void *, const void *, size_t);
static memcmp_t original_memcmp = NULL;

int WINAPI detour_memcmp(const void *a, const void *b, size_t n) {
    OutputDebugStringA("[hook] memcmp called");
    int r = original_memcmp(a, b, n);
    return r;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        MH_Initialize();
        MH_CreateHook(GetProcAddress(GetModuleHandleA("msvcrt.dll"), "memcmp"),
                      &detour_memcmp, (LPVOID *)&original_memcmp);
        MH_EnableHook(MH_ALL_HOOKS);
    }
    return TRUE;
}
```

编译成 DLL 后用注入器加载，或用 ​`frida -f challenge.exe -l loader.js`​ 里的 ​`Module.load` 加载。

## 0x07 Linux 侧同类题

Linux 上对应的是 GOT/PLT hook：

```bash
objdump -R ./challenge | grep -E "memcmp|strcmp"   # 看 GOT 项
readelf -r ./challenge | head
ltrace ./challenge                                 # 直接看库调用
```

题目自己改 GOT 时，​`mprotect`​ 是痕迹；也可以在 ​`LD_PRELOAD` 里伪造同签名函数，把参数打出来：

```c
int memcmp(const void *a, const void *b, size_t n) {
    write(2, a, n);
    write(2, "\n", 1);
    return 0;
}
```

编译 ​`gcc -shared -fPIC -o fake.so fake.c`​，​`LD_PRELOAD=./fake.so ./challenge`。

## 0x08 常见坑

- **x86 与 x64 调用约定不同**：x64 前四个参数在 rcx/rdx/r8/r9，x86 stdcall 全在栈上，Frida 的 ​`args[]` 两边都能用，但手写汇编/内联补丁要分清。
- **​`VirtualProtect`​**​ **的 prot 值**：​`0x40`​ 是 ​`PAGE_EXECUTE_READWRITE`​，​`0x04`​ 是 ​`PAGE_READWRITE`​，​`0x20`​ 是 ​`PAGE_EXECUTE_READ`，判断错会漏掉写入点。
- **inline hook 长度不够**：x64 用 ​`mov rax, imm64; jmp rax`​ 要 12 字节，​`jmp [rip+0]` 要 14 字节；只覆盖 5 字节会把后面的指令切碎。
- **恢复后忘了** ​**​`FlushInstructionCache`​**：代码改了但 CPU 还执行旧指令，表现为"恢复了没生效"。
- **内存 dump 与文件偏移**：PE 是 ​`FileAlignment`​ 与 ​`SectionAlignment` 两套对齐，直接按文件偏移改内存会错位。
- **IAT 加密**：有些题启动时先解密 IAT，静态看到的全是垃圾指针，要在解密后 dump。
- **隐藏函数在异常处理里**：VEH/SEH 注册的回调地址不在任何模块，​`Process.enumerateRanges`​ 找 ​`rwx`​ 时容易漏，按 ​`PAGE_EXECUTE_READ` 也扫一遍。
- **hook 了** ​**​`memcmp`​**​ **但没进隐藏函数**：可能挂的是 ​`memcmp`​ 的 syscall stub 或者 CRT 内部实现，确认实际调用的是哪个模块的哪个函数（​`frida-trace -i "memcmp"`）。

## 0x09 复盘模板

```text
题目：
文件：exe / dll / so，架构 x86 / x64 / arm64
hook 类型：IAT / EAT / Inline / GOT
被 hook 的函数：memcmp @ msvcrt.dll（或 ntdll!NtXxx）
痕迹：函数头 E9 → 目标 0x...
权限修改点：VirtualProtect(0x..., 0x..., 0x40)
隐藏函数地址：0x...（模块外 / RWX）
隐藏函数作用：解密 / 比较 / 反调试
参数结构：arg0=输入，arg1=目标串
dump 方式：内存镜像 diff / Frida attach
恢复方式：还原 IAT 项 / 写回原始字节
FLAG：
踩坑：
```

## 0x0a 参考

- [IAT Hook 原理与实现](https://www.codeproject.com/Articles/2082/API-Hooking-revealed)
- [MinHook](https://github.com/TsudaKageyu/minhook)
- [pe-sieve：检测进程内 hook 与注入](https://github.com/hasherezade/pe-sieve)

0x03 / 0x04 的脚本合并成了可直接跑的版本：​`scripts/api_hook_trace.js`​。在 Windows 上 ​`frida -f challenge.exe -l api_hook_trace.js`，会同时打印权限修改、被 hook 的系统函数入口字节，以及 RWX 区域里的函数候选。
