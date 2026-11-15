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
