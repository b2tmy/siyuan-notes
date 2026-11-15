# 笔记总览

由 SiYuan 导出的 Markdown，按笔记本分目录。空笔记本与「未命名文档」已在导出时过滤掉。

重新导出：`python export.py`（需要 SiYuan 内核在 127.0.0.1:6806 运行）。

## cryption

- [00 cryption](cryption/00%20cryption.md)
- [01 XOR：最简单但最容易被魔改的异或流](cryption/01%20XOR：最简单但最容易被魔改的异或流.md)
- [02 RC4：KSA + PRGA，重点盯状态数组和丢弃字节](cryption/02%20RC4：KSA%20+%20PRGA，重点盯状态数组和丢弃字节.md)
- [03 TEA：32 轮 Feistel，字节序、delta 和无符号溢出是生死线](cryption/03%20TEA：32%20轮%20Feistel，字节序、delta%20和无符号溢出是生死线.md)
- [04 DES：Feistel、模式、填充与弱密钥](cryption/04%20DES：Feistel、模式、填充与弱密钥.md)
- [05 AES：状态矩阵与模式优先，魔改题要抓 AddRoundKey 前后状态](cryption/05%20AES：状态矩阵与模式优先，魔改题要抓%20AddRoundKey%20前后状态.md)
- [06 SMC：不是一种固定密码，而是自修改代码场景](cryption/06%20SMC：不是一种固定密码，而是自修改代码场景.md)
- [07 Python CTF 逆向常用数据转换与 Flag 输出](cryption/07%20Python%20CTF%20逆向常用数据转换与%20Flag%20输出.md)
- [08 故障复盘：空白笔记本的根因与防复发](cryption/08%20故障复盘：空白笔记本的根因与防复发.md)
- [09 Z3：把校验逻辑翻译成约束，而不是手撸爆破](cryption/09%20Z3：把校验逻辑翻译成约束，而不是手撸爆破.md)
- [10 CTF 里的 API Hook 题：IAT 与 Inline Hook 隐藏的加密函数](cryption/10%20CTF%20里的%20API%20Hook%20题：IAT%20与%20Inline%20Hook%20隐藏的加密函数.md)

## Resever_learning

- [SSH 协议、密钥认证与安全加固实战](Resever_learning/SSH%20协议、密钥认证与安全加固实战.md)
- [逆向工程基础](Resever_learning/逆向工程基础.md)
- [汇编语言与调用约定](Resever_learning/汇编语言与调用约定.md)
- [PE 文件结构](Resever_learning/PE%20文件结构.md)
- [Windows 系统原理](Resever_learning/Windows%20系统原理.md)
- [静态分析](Resever_learning/静态分析.md)
- [动态调试](Resever_learning/动态调试.md)
- [C/C++ 逆向](Resever_learning/C-C++%20逆向.md)
- [编译器特征识别](Resever_learning/编译器特征识别.md)
- [脱壳与壳分析](Resever_learning/脱壳与壳分析.md)
- [反调试与反反调试](Resever_learning/反调试与反反调试.md)
- [代码混淆与去混淆](Resever_learning/代码混淆与去混淆.md)
- [加密算法识别](Resever_learning/加密算法识别.md)
- [Android 逆向](Resever_learning/Android%20逆向.md)
- [恶意代码分析](Resever_learning/恶意代码分析.md)
- [漏洞分析](Resever_learning/漏洞分析.md)
- [常用工具手册](Resever_learning/常用工具手册.md)
- [实战案例与复盘](Resever_learning/实战案例与复盘.md)
- [个人经验、技巧和易错点](Resever_learning/个人经验、技巧和易错点.md)

## Agent开发

- [Agent 开发知识库](Agent开发/Agent%20开发知识库.md)
- [01 第一章 初识智能体](Agent开发/01%20第一章%20初识智能体.md)
- [02 第二章 智能体发展史](Agent开发/02%20第二章%20智能体发展史.md)
- [03 第三章 大语言模型基础](Agent开发/03%20第三章%20大语言模型基础.md)
- [04 第四章 智能体经典范式构建](Agent开发/04%20第四章%20智能体经典范式构建.md)
- [05 第五章 基于低代码平台的智能体搭建](Agent开发/05%20第五章%20基于低代码平台的智能体搭建.md)
- [06 第六章 框架开发实践](Agent开发/06%20第六章%20框架开发实践.md)
- [07 第七章 构建你的Agent框架](Agent开发/07%20第七章%20构建你的Agent框架.md)
- [08 第八章 记忆与检索](Agent开发/08%20第八章%20记忆与检索.md)
- [09 第九章 上下文工程](Agent开发/09%20第九章%20上下文工程.md)
- [10 第十章 智能体通信协议](Agent开发/10%20第十章%20智能体通信协议.md)
- [11 第十一章 Agentic-RL](Agent开发/11%20第十一章%20Agentic-RL.md)
- [12 第十二章 智能体性能评估](Agent开发/12%20第十二章%20智能体性能评估.md)
- [13 第十三章 智能旅行助手](Agent开发/13%20第十三章%20智能旅行助手.md)
- [14 第十四章 自动化深度研究智能体](Agent开发/14%20第十四章%20自动化深度研究智能体.md)
- [15 第十五章 构建赛博小镇](Agent开发/15%20第十五章%20构建赛博小镇.md)
- [16 自建Agent路线图](Agent开发/16%20自建Agent路线图.md)

## frida_hook

- [00 frida_hook](frida_hook/00%20frida_hook.md)
- [01 环境、frida-server 与命令行速查](frida_hook/01%20环境、frida-server%20与命令行速查.md)
- [02 Java 层：perform、use、overload、implementation](frida_hook/02%20Java%20层：perform、use、overload、implementation.md)
- [03 Native 层：Module、Interceptor、Memory、NativeFunction](frida_hook/03%20Native%20层：Module、Interceptor、Memory、NativeFunction.md)
- [04 常用 Hook 模板合集](frida_hook/04%20常用%20Hook%20模板合集.md)
- [05 排查：版本、ClassLoader、时机与对抗](frida_hook/05%20排查：版本、ClassLoader、时机与对抗.md)
- [06 CTF 逆向里的 Hook 题：题型、套路与解题脚本](frida_hook/06%20CTF%20逆向里的%20Hook%20题：题型、套路与解题脚本.md)

## pwn

- [00 pwn](pwn/00%20pwn.md)
- [01 汇编基础：寄存器、指令、调用约定与栈帧](pwn/01%20汇编基础：寄存器、指令、调用约定与栈帧.md)
- [02 栈溢出：从覆盖返回地址到第一个 shell](pwn/02%20栈溢出：从覆盖返回地址到第一个%20shell.md)
