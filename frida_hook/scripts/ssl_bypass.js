/*
 * SSL Pinning 绕过合集：按需注释掉不相关的段
 *   frida -U -f com.example.app -l ssl_bypass.js --no-pause
 */
"use strict";

function log(msg) { console.log("[ssl] " + msg); }

Java.perform(function () {
    // 1. 系统 TrustManager（大多数 HttpURLConnection / OkHttp 走这里）
    try {
        var TMI = Java.use("com.android.org.conscrypt.TrustManagerImpl");
        TMI.verifyChain.implementation = function (untrustedChain, anchorChain, host, clientAuth, ocsp, sct) {
            log("TrustManagerImpl.verifyChain: " + host);
            return untrustedChain;
        };
        log("hooked TrustManagerImpl");
    } catch (e) {
        log("TrustManagerImpl not found: " + e);
    }

    // 2. 替换 SSLContext 的 TrustManager
    try {
        var X509TM = Java.use("javax.net.ssl.X509TrustManager");
        var FakeTM = Java.registerClass({
            name: "com.example.FakeTrustManager",
            implements: [X509TM],
            methods: {
                checkClientTrusted: function (chain, authType) {},
                checkServerTrusted: function (chain, authType) {},
                getAcceptedIssuers: function () { return []; }
            }
        });
        var SSLContext = Java.use("javax.net.ssl.SSLContext");
        SSLContext.init.overload(
            "[Ljavax.net.ssl.KeyManager;",
            "[Ljavax.net.ssl.TrustManager;",
            "java.security.SecureRandom"
        ).implementation = function (km, tm, sr) {
            log("SSLContext.init hooked");
            this.init(km, [FakeTM.$new()], sr);
        };
        log("hooked SSLContext.init");
    } catch (e) {
        log("SSLContext hook failed: " + e);
    }

    // 3. OkHttp CertificatePinner
    try {
        var Pinner = Java.use("okhttp3.CertificatePinner");
        Pinner.check.overload("java.lang.String", "java.util.List").implementation = function (host, peers) {
            log("CertificatePinner.check: " + host);
        };
        log("hooked CertificatePinner.check");
    } catch (e) {
        log("CertificatePinner.check not found: " + e);
    }

    try {
        var Pinner2 = Java.use("okhttp3.CertificatePinner");
        Pinner2.check$okhttp.overload("java.lang.String", "kotlin.jvm.functions.Function0").implementation = function (host, f) {
            log("CertificatePinner.check$okhttp: " + host);
        };
        log("hooked CertificatePinner.check$okhttp");
    } catch (e) {
        log("check$okhttp not found: " + e);
    }

    // 4. 主机名校验
    try {
        var OkVerifier = Java.use("okhttp3.internal.tls.OkHostnameVerifier");
        OkVerifier.verify.overload("java.lang.String", "javax.net.ssl.SSLSession").implementation = function (host, session) {
            log("OkHostnameVerifier.verify: " + host);
            return true;
        };
        log("hooked OkHostnameVerifier");
    } catch (e) {
        log("OkHostnameVerifier not found: " + e);
    }
});
