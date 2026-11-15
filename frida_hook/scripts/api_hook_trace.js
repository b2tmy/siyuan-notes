/*
 * Windows 系统 API hook 题：抓权限修改 + 挖隐藏加密函数
 *   frida -f challenge.exe -l api_hook_trace.js
 *
 * 目标进程是 Windows PE。输出分三块：
 *   1) 权限/内存分配调用（VirtualProtect / VirtualAlloc / FlushInstructionCache）
 *   2) 被 hook 的系统函数入口字节与跳转目标
 *   3) RWX 区域里的函数候选
 */
"use strict";

var WATCH = [
    { dll: "kernel32.dll", name: "VirtualProtect" },
    { dll: "kernel32.dll", name: "VirtualAlloc" },
    { dll: "kernel32.dll", name: "VirtualProtectEx" },
    { dll: "kernel32.dll", name: "FlushInstructionCache" },
    { dll: "kernel32.dll", name: "GetProcAddress" }
];

var HOOK_PROBES = [
    { dll: "msvcrt.dll", name: "memcmp" },
    { dll: "msvcrt.dll", name: "strcmp" },
    { dll: "kernel32.dll", name: "IsDebuggerPresent" },
    { dll: "ntdll.dll", name: "NtQueryInformationProcess" }
];

function hookExport(dll, name, onEnter, onLeave) {
    var addr = Module.findExportByName(dll, name);
    if (!addr) {
        console.log("[-] " + dll + "!" + name + " not found");
        return;
    }
    Interceptor.attach(addr, { onEnter: onEnter, onLeave: onLeave });
    console.log("[*] watching " + dll + "!" + name);
}

// ------------------------------------------------------------ 1. 权限修改
WATCH.forEach(function (w) {
    hookExport(w.dll, w.name, function (args) {
        if (w.name === "GetProcAddress") {
            try { console.log("[gpa] " + args[1].readCString()); } catch (e) {}
            return;
        }
        var target = args[0];
        var size = args[1].toInt32();
        var prot = args[2].toInt32();
        console.log("[" + w.name + "] addr=" + target +
                    " size=0x" + size.toString(16) +
                    " prot=0x" + prot.toString(16));
        if (prot & 0x40) {
            this.dumpAddr = target;
            this.dumpSize = Math.min(size, 256);
        }
    }, function () {
        if (this.dumpAddr) {
            console.log("[dump] " + this.dumpAddr);
            console.log(hexdump(this.dumpAddr, { length: this.dumpSize }));
            this.dumpAddr = null;
        }
    });
});

// ------------------------------------------------------------ 2. 入口被改？
function probeInlineHook(dll, name) {
    var p = Module.findExportByName(dll, name);
    if (!p) return;

    var head = p.readByteArray(16);
    var b = new Uint8Array(head);
    var hex = Array.prototype.map.call(b, function (x) {
        return ("0" + x.toString(16)).slice(-2);
    }).join(" ");

    var note = "";
    if (b[0] === 0xE9) {
        var rel = p.add(1).readS32();
        note = " -> jmp " + p.add(5).add(rel);
    } else if (b[0] === 0xFF && b[1] === 0x25) {
        note = " -> jmp [rip+disp]";
    } else if (b[0] === 0x48 && b[1] === 0xB8) {
        note = " -> mov rax, imm64; jmp rax";
    } else {
        note = " (looks clean)";
    }
    console.log("[probe] " + dll + "!" + name + " : " + hex + note);

    if (b[0] === 0xE9) {
        var target = p.add(5).add(p.add(1).readS32());
        console.log("[hidden] " + target + " bytes: " + target.readByteArray(16));
    }
}

HOOK_PROBES.forEach(function (h) { probeInlineHook(h.dll, h.name); });

// ------------------------------------------------------------ 3. RWX 扫描
Process.enumerateRanges("rwx").forEach(function (r) {
    console.log("[rwx] " + r.base + " size=0x" + r.size.toString(16));
    try {
        var hits = Memory.scanSync(r.base, Math.min(r.size, 0x20000), "55 48 89 E5");
        hits.forEach(function (hit) {
            console.log("  [func?] " + hit.address);
        });
    } catch (e) {}
});

console.log("[*] pid=" + Process.id + " arch=" + Process.arch);
