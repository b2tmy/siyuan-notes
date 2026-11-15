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
  mkdir -p out/zygisk
  cp "build/$abi/demozygisk.so" "out/zygisk/$abi.so"
done
cp module.prop out/
