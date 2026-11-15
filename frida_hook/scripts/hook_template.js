/*
 * Frida 基础模板：改下面三行就能跑
 *   frida -U -f com.example.app -l hook_template.js --no-pause
 */
"use strict";

// ---------------- 配置 ----------------
var PKG = "com.example.app";
var JAVA_CLASS = "com.example.app.Check";   // Java 侧目标类，空字符串则跳过
var NATIVE_LIB = "libnative.so";            // so 名，空字符串则跳过
var NATIVE_FUNCS = [
    // { name: "check_flag", args: ["str", "int"] }
];

// ---------------- Java 侧 ----------------
function hookJava() {
    if (!JAVA_CLASS) return;
    Java.perform(function () {
        var Cls = Java.use(JAVA_CLASS);
        console.log("[*] class loaded: " + Cls);

        Cls.class.getDeclaredMethods().forEach(function (m) {
            var name = m.getName();
            var over = Cls[name];
            if (!over || !over.overloads) return;

            over.overloads.forEach(function (o) {
                var sig = o.argumentTypes.map(function (t) {
                    return t.className;
                }).join(", ");
                console.log("    " + name + "(" + sig + ")");

                o.implementation = function () {
                    var args = Array.prototype.slice.call(arguments);
                    console.log("[+] " + name + "(" + args.join(", ") + ")");
                    var ret = o.apply(this, arguments);
                    console.log("[+] " + name + " -> " + ret);
                    return ret;
                };
            });
        });
    });
}

// ---------------- Native 侧 ----------------
function readArg(ptrArg, type) {
    try {
        if (type === "str") return JSON.stringify(ptrArg.readUtf8String());
        if (type === "int") return ptrArg.toInt32();
        if (type === "ptr") return ptrArg.toString();
        return ptrArg.toString();
    } catch (e) {
        return "<read error>";
    }
}

function hookNative(mod) {
    NATIVE_FUNCS.forEach(function (desc) {
        var addr = null;
        try {
            addr = Module.getExportByName(mod.name, desc.name);
        } catch (e) {
            console.log("[-] symbol not found: " + desc.name);
            return;
        }

        Interceptor.attach(addr, {
            onEnter: function (args) {
                var out = [];
                for (var i = 0; i < desc.args.length; i++) {
                    out.push(readArg(args[i], desc.args[i]));
                }
                console.log("[n] " + desc.name + "(" + out.join(", ") + ")");
                this.t0 = Date.now();
            },
            onLeave: function (retval) {
                var cost = Date.now() - this.t0;
                console.log("[n] " + desc.name + " -> " + retval + " (" + cost + "ms)");
            }
        });
        console.log("[*] hooked " + mod.name + "!" + desc.name + " @ " + addr);
    });
}

function waitModule(name, cb) {
    var m = Process.findModuleByName(name);
    if (m) { cb(m); return; }

    var dlopen = Module.findExportByName(null, "android_dlopen_ext");
    if (dlopen) {
        Interceptor.attach(dlopen, {
            onEnter: function (args) { this.path = args[0].readCString(); },
            onLeave: function () {
                if (this.path && this.path.indexOf(name) >= 0) {
                    var mod = Process.findModuleByName(name);
                    if (mod) cb(mod);
                }
            }
        });
    }

    // 兜底轮询，防止 dlopen 没拦到
    var timer = setInterval(function () {
        var mod = Process.findModuleByName(name);
        if (mod) { clearInterval(timer); cb(mod); }
    }, 200);
}

// ---------------- 入口 ----------------
console.log("[*] pid=" + Process.id + " arch=" + Process.arch);

if (NATIVE_LIB && NATIVE_FUNCS.length) {
    waitModule(NATIVE_LIB, function (mod) {
        console.log("[*] module " + mod.name + " base=" + mod.base + " size=" + mod.size);
        hookNative(mod);
    });
}

if (JAVA_CLASS) {
    // Java 环境在 spawn 早期可能还没就绪
    setTimeout(function () {
        try { hookJava(); } catch (e) { console.log("[-] java hook failed: " + e); }
    }, 500);
}
