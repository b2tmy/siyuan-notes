/*
 * CTF 逆向 hook 题通用骨架
 *   frida -U -f com.example.app -l ctf_hook_solution.js --no-pause
 *
 * 用法：改 CONFIG 里的类名/方法名/so 名，先跑打印，确认打得到再改行为。
 */
"use strict";

var CONFIG = {
    className: "com.example.app.Check",   // Java 校验类
    method: "verify",                     // 方法名
    signature: ["java.lang.String"],      // 重载签名，空数组表示无参
    libName: "libnative.so",              // native 校验所在 so
    nativeFunc: "check_flag",             // 导出函数名，留空则不挂
    hookNativeJni: true,                  // 是否打印 RegisterNatives 注册表
    forceReturn: null                     // 打印阶段保持 null；确认后填 true/1
};

// ---------------------------------------------------------------- Java
function hookJava() {
    if (!CONFIG.className) return;
    Java.perform(function () {
        var C = Java.use(CONFIG.className);

        // 先看这个类到底有哪些方法，签名对不上时靠它
        C.class.getDeclaredMethods().forEach(function (m) {
            console.log("[class] " + m.getName());
        });

        var target = CONFIG.signature.length
            ? C[CONFIG.method].overload.apply(C[CONFIG.method], CONFIG.signature)
            : C[CONFIG.method].overload();

        target.implementation = function () {
            var args = Array.prototype.slice.call(arguments);
            console.log("[java] " + CONFIG.method + "(" + args.join(", ") + ")");

            var ret = target.apply(this, arguments);
            console.log("[java] -> " + ret);

            if (CONFIG.forceReturn !== null) {
                console.log("[java] forced -> " + CONFIG.forceReturn);
                return CONFIG.forceReturn;
            }
            return ret;
        };
    });
}

// ---------------------------------------------------------------- Native
function hookNative() {
    if (!CONFIG.libName || !CONFIG.nativeFunc) return;

    var addr = Module.findExportByName(CONFIG.libName, CONFIG.nativeFunc);
    if (!addr) {
        console.log("[-] export not found, try RegisterNatives scan");
        return;
    }

    Interceptor.attach(addr, {
        onEnter: function (args) {
            var out = [];
            for (var i = 0; i < 4; i++) {
                try { out.push(args[i].toString()); } catch (e) {}
            }
            console.log("[native] " + CONFIG.nativeFunc + "(" + out.join(", ") + ")");
            console.log(Thread.backtrace(this.context, Backtracer.ACCURATE)
                .map(DebugSymbol.fromAddress).join("\n"));
        },
        onLeave: function (retval) {
            console.log("[native] -> " + retval);
        }
    });
    console.log("[*] hooked " + CONFIG.libName + "!" + CONFIG.nativeFunc);
}

// ---------------------------------------------------------------- RegisterNatives
function scanRegisterNatives() {
    var libart = Process.findModuleByName("libart.so");
    if (!libart) return;

    libart.enumerateSymbols().forEach(function (s) {
        if (s.name.indexOf("RegisterNatives") < 0) return;
        console.log("[*] " + s.name + " @ " + s.address);

        Interceptor.attach(s.address, {
            onEnter: function (args) {
                var methods = args[2];
                var count = args[3].toInt32();
                for (var i = 0; i < count; i++) {
                    var base = methods.add(i * Process.pointerSize * 3);
                    var name = base.readPointer().readCString();
                    var sig = base.add(Process.pointerSize).readPointer().readCString();
                    var fn = base.add(Process.pointerSize * 2).readPointer();
                    console.log("    " + name + sig + " -> " + fn);
                }
            }
        });
    });
}

// ---------------------------------------------------------------- 入口
console.log("[*] pid=" + Process.id + " arch=" + Process.arch);
hookJava();
hookNative();
if (CONFIG.hookNativeJni) {
    try { scanRegisterNatives(); } catch (e) { console.log("[-] scan failed: " + e); }
}
