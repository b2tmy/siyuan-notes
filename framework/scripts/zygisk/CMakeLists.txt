cmake_minimum_required(VERSION 3.18)
project(demozygisk CXX)

add_library(demozygisk SHARED module.cpp)
target_compile_features(demozygisk PRIVATE cxx_std_17)
target_include_directories(demozygisk PRIVATE ${ZYGISK_INCLUDE})
target_link_libraries(demozygisk PRIVATE log)

set_target_properties(demozygisk PROPERTIES PREFIX "")
