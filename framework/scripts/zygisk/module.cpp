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
