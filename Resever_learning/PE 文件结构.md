---
title: PE 文件结构
date: 2026-09-28T14:05:11+08:00
lastmod: 2026-10-08T17:30:00+08:00
---

# PE 文件结构

# PE 文件结构详解：从磁盘文件到进程映像

## 0x00 前言

PE（Portable Executable）是 Windows 平台上 EXE、DLL、SYS、OCX 等映像文件使用的格式。逆向分析 PE 时，真正需要掌握的不是结构体名称，而是加载器如何把磁盘文件转换为内存映像，以及文件偏移（FOA）、相对虚拟地址（RVA）和虚拟地址（VA）之间如何建立映射。

本文按照加载器处理文件的顺序，从 MZ 头开始，逐层分析 DOS 头、NT 头、节表、数据目录、导入导出、重定位、TLS、异常、资源、签名和 Overlay，并穿插逆向分析中最容易出错的地方。

## 0x01 PE 文件整体布局

一个典型 PE 文件可以抽象为：

```text
DOS Header
DOS Stub
Rich Header（可选）
PE\\0\\0 Signature
IMAGE_FILE_HEADER
IMAGE_OPTIONAL_HEADER
IMAGE_SECTION_HEADER[]
Section Raw Data
Overlay（可选）
```

头部描述文件应当如何映射到内存，节数据保存代码、数据、资源和各种表。节名只是约定，Windows 加载器主要依据节表中的地址、大小和属性工作，因此不能仅凭 `.text`、`.data` 等名称判断内容。

## 0x02 DOS Header：从 MZ 到 e_lfanew

PE 文件开头是 IMAGE_DOS_HEADER。`e_magic` 位于偏移 0x00，正常值为 0x5A4D，小端显示为 `4D 5A`，对应 ASCII 字符 `MZ`。检测到 MZ 只能说明文件可能是 DOS/PE 文件，还不能证明它是合法 PE。

偏移 0x3C 处的 `e_lfanew` 是后续解析的关键，它保存 NT 头相对于文件开头的偏移。解析器应先检查 e_lfanew 是否为负数、是否超出文件长度，再根据它定位 PE 签名。

```c
PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)buffer;
if (dos->e_magic != IMAGE_DOS_SIGNATURE) return FALSE;
PIMAGE_NT_HEADERS nt =
    (PIMAGE_NT_HEADERS)(buffer + dos->e_lfanew);
```

DOS Stub 位于 DOS 头之后，常见字符串是 `This program cannot be run in DOS mode.`。现代 Windows 加载器通常不会执行它，但它仍可能包含 Rich Header 或其他附加数据。

## 0x03 Rich Header 与 PE Signature

微软工具链生成的文件经常在 DOS Stub 与 NT 头之间保存 Rich Header。它可能记录编译器、链接器和工具链版本信息，但不是 PE 规范的必需部分，也可能被删除或伪造。

根据 e_lfanew 定位后，应当看到四字节签名：

```text
50 45 00 00
```

也就是 `PE\\0\\0`。签名之后依次是 COFF File Header 和 Optional Header。

## 0x04 IMAGE_FILE_HEADER：架构与文件属性

`IMAGE_FILE_HEADER` 中最常用的字段包括：

- `Machine`：目标架构。0x014C 常见于 x86，0x8664 常见于 x64。
- `NumberOfSections`：节表项数量，每项通常为 40 字节。
- `TimeDateStamp`：传统链接时间戳，但可以被修改，不能单独当作可信时间证据。
- `SizeOfOptionalHeader`：可选头实际长度，定位节表时应使用它，不要写死。
- `Characteristics`：是否为可执行映像、DLL、系统文件以及是否剥离重定位等属性。

任何数量和大小字段都不能直接信任。解析节表前，应验证：

```text
节表起始位置 + NumberOfSections × 40 <= 文件大小
```

## 0x05 Optional Header：PE 的加载参数

Optional Header 对普通映像并不是真正“可选”。加载器依赖其中的入口点、首选基址、对齐参数、映像大小和数据目录。

首先根据 `Magic` 判断布局：

```text
0x10B：PE32
0x20B：PE32+
```

PE32+ 通常用于 x64，但并不表示所有字段都简单变成 64 位。PE32+ 没有 BaseOfData，ImageBase、栈和堆相关字段的宽度会发生变化，导入 Thunk 和重定位类型也要按 64 位处理。

### 5.1 入口点与映像基址

`AddressOfEntryPoint` 保存入口点 RVA，不是文件偏移。若映像实际加载地址为 ImageBase，则：

```text
EntryPoint VA = ImageBase + AddressOfEntryPoint
```

EXE 的入口点通常是运行库启动代码，不一定直接对应 `main`；DLL 的入口点也可能先经过运行库包装。加壳程序的入口点往往先进入壳代码。

`ImageBase` 是首选装载地址。启用 ASLR 或该地址已被占用时，模块可能被加载到其他位置，此时需要应用重定位。

### 5.2 对齐、大小与子系统

- `SectionAlignment`：节映射到内存后的对齐，常见为 0x1000。
- `FileAlignment`：节在磁盘中的对齐，常见为 0x200。
- `SizeOfImage`：整个映像映射到内存后的对齐总大小。
- `SizeOfHeaders`：头部在文件和内存中占用的对齐大小。
- `Subsystem`：GUI、控制台、Native、EFI 等运行子系统。
- `DllCharacteristics`：ASLR、DEP/NX、CFG、高熵 VA 等标志。

磁盘和内存使用不同对齐粒度，正是两种布局不能混用的根本原因。

## 0x06 节表 IMAGE_SECTION_HEADER

每个节表项描述节名、内存位置、磁盘位置、大小和权限。重点字段如下：

- `Name`：最多 8 字节，未必以零结尾。
- `VirtualAddress`：节在内存中的 RVA 起点。
- `Misc.VirtualSize`：节在内存中的逻辑大小。
- `PointerToRawData`：节在文件中的起始偏移。
- `SizeOfRawData`：节在文件中的原始数据大小。
- `Characteristics`：代码、数据、可读、可写、可执行等属性。

`.text` 常存代码，`.rdata` 常存只读数据、字符串和虚表，`.data` 常存可写全局变量，`.rsrc` 保存资源，`.reloc` 保存重定位。但节名可以修改、合并或伪造，判断内容时应结合字节、交叉引用、权限和熵。

`VirtualSize` 与 `SizeOfRawData` 不相等是正常现象。若 VirtualSize 大于 SizeOfRawData，加载器会把文件中已有的数据复制到内存，并将剩余区域零初始化，这通常对应未初始化全局变量。

## 0x07 FOA、RVA 与 VA

这是 PE 分析中最容易混淆的部分：

```text
FOA：数据在磁盘文件中的偏移
RVA：数据相对于模块基址的内存偏移
VA ：进程虚拟地址空间中的实际地址

VA  = ImageBase + RVA
```

若 RVA 落在某个节中，通常使用：

```text
FOA = PointerToRawData
    + (RVA - VirtualAddress)
```

查找节时可用：

```text
VirtualAddress <= RVA < VirtualAddress + max(VirtualSize, SizeOfRawData)
```

但如果目标位于 `VirtualSize > SizeOfRawData` 形成的零初始化区域，它在内存中存在，在磁盘中却没有对应字节，不能强行转换成文件偏移。头部区域的 RVA 通常可以直接对应同值 FOA，但必须确认它位于 SizeOfHeaders 范围内。

## 0x08 Data Directory：关键表的索引

Optional Header 尾部包含数据目录数组，每一项由 `VirtualAddress` 和 `Size` 组成。常见目录包括：

```text
Export
Import
Resource
Exception
Security
Base Relocation
Debug
TLS
Load Config
IAT
Delay Import
CLR Runtime Header
```

通常 VirtualAddress 是 RVA，但 `IMAGE_DIRECTORY_ENTRY_SECURITY` 是重要例外：其 VirtualAddress 实际按文件偏移解释，因为 Authenticode 证书表通常不映射到进程内存。

解析数据目录时应先检查目录数量、RVA、Size、整数溢出和文件边界，再执行地址转换。目录并不一定位于同名节中。

## 0x09 导入表与 IAT

Import Directory 由一组 `IMAGE_IMPORT_DESCRIPTOR` 组成，每项描述一个依赖 DLL。`Name` 指向 DLL 名称；`OriginalFirstThunk` 通常指向名称/序号表；`FirstThunk` 指向 IAT。

文件尚未加载时，IAT 中通常保存导入引用。模块加载后，加载器会载入目标 DLL、查找导出函数，并把实际地址写入 IAT，代码通过间接调用访问外部 API：

```text
call [IAT_CreateFileW]
```

导入可以按名称或序号完成。若 OriginalFirstThunk 为零，需要结合 FirstThunk 解析；如果观察的是已经完成加载修复的内存映像，FirstThunk 可能已经被实际函数地址覆盖。

静态导入表不能代表全部 API 使用情况。延迟导入、GetProcAddress、API Set、哈希解析和手动映射都会让真实依赖隐藏在标准导入表之外。

## 0x0A 导出表

Export Directory 通常包含三张表：函数地址表、名称指针表和名称序号表。对于第 i 个名称：

```text
函数名称 RVA = AddressOfNames[i]
函数索引     = AddressOfNameOrdinals[i]
函数 RVA     = AddressOfFunctions[函数索引]
导出序号     = Base + 函数索引
```

`NumberOfFunctions` 与 `NumberOfNames` 不一定相等，因为部分函数可能只按序号导出。若函数 RVA 落在导出目录自身范围内，通常表示 Forwarded Export，例如转发到其他 DLL 的字符串，而不是直接代码地址。

## 0x0B 基址重定位

当实际加载地址不同于首选 ImageBase 时，加载器计算：

```text
Delta = ActualImageBase - PreferredImageBase
```

然后遍历 Base Relocation Directory。每个重定位块包含页 RVA、块大小和若干 16 位条目：

```text
高 4 位：重定位类型
低 12 位：页内偏移
```

常见类型是 x86 的 `HIGHLOW` 和 x64 的 `DIR64`，`ABSOLUTE` 通常只是填充项。ASLR 是否真正有效，需要同时检查 DYNAMIC_BASE 标志、重定位目录是否存在以及实际加载行为。

## 0x0C TLS：入口点之前的执行机会

TLS Directory 描述线程局部存储模板、索引和回调数组。TLS 回调可以在普通 AddressOfEntryPoint 之前执行，因此分析反调试、解密、自修改和初始化逻辑时不能只盯着入口点。

建议检查：

1. TLS 目录是否存在；
2. 回调数组地址是否有效；
3. 回调是否指向可执行区域；
4. 回调是否修改 IAT、权限或代码；
5. 回调结束后是否跳转到真实入口点。

## 0x0D 异常目录与 Load Config

x64 PE 的 Exception Directory 通常关联 `.pdata` 中的 `RUNTIME_FUNCTION`，记录函数起始、结束和展开信息，可用于异常处理、栈展开和调用栈恢复。

Load Config 可能包含 Security Cookie、SafeSEH、CFG 函数表和 Guard Flags 等。结构长度会随系统和 SDK 变化，读取时应尊重数据目录的 Size，不能无条件按本机头文件大小读取。

## 0x0E 资源、调试和签名

资源目录采用多级树，可包含图标、版本信息、清单、字符串、对话框和嵌入文件。Debug Directory 可能包含 CodeView 信息、PDB 路径、GUID 和 Age，从而暴露工程目录和构建环境线索。

Security Directory 指向 Authenticode 证书表。证书区域通常不作为普通节映射到内存，修改已签名范围通常会导致签名验证失败。文件末尾数据还需要区分证书表、Overlay、安装包内容和自定义附加数据。

## 0x0F Overlay 与加壳线索

Overlay 是最后一个节原始数据之后、没有被节表描述的内容。它可能是安装包、压缩数据、配置、证书或附加载荷，不能仅凭存在 Overlay 就认定文件恶意。

常见加壳线索包括：

- 导入函数极少；
- 入口点位于高熵或可写节；
- 节名异常或节数量异常；
- 入口附近存在解压循环；
- 运行后生成新代码；
- 通过跳转到 OEP 恢复原始流程。

这些线索需要结合动态调试和内存映像验证，不能单独作为结论。

## 0x10 Windows 加载 PE 的简化流程

```text
验证 MZ 和 e_lfanew
验证 PE Signature
检查架构和头部边界
为 SizeOfImage 预留地址空间
映射 Headers 和各节
设置节内存属性
必要时处理重定位
加载依赖 DLL
解析导入并填写 IAT
处理 TLS 和运行时结构
注册异常信息
执行入口点
```

真实加载过程还会涉及 API Set、SxS、激活上下文、WOW64、CFG、签名策略和加载器锁，但上述流程足以建立分析框架。

## 0x11 常见解析错误

### 错误一：直接使用 buffer + RVA

磁盘文件不是内存映像，不能把所有 RVA 直接当作文件偏移。应先根据节表执行 RVA 到 FOA 的转换。

### 错误二：写死 Optional Header 大小

应使用 `SizeOfOptionalHeader` 定位节表，否则无法兼容 PE32+ 和非标准布局。

### 错误三：只依据节名判断内容

节名可以修改，真正的代码和数据应结合权限、字节特征、交叉引用和运行时行为判断。

### 错误四：忽略整数溢出

不要只写 `offset + size <= fileSize`。更稳妥的检查方式是：

```c
if (offset > fileSize) return FALSE;
if (size > fileSize - offset) return FALSE;
```

### 错误五：把 Security Directory 当作 RVA

安全目录的 VirtualAddress 是文件偏移，这是数据目录中最典型的特殊规则。

## 0x12 实战检查清单

```text
1. 验证 MZ、e_lfanew 和 PE\\0\\0
2. 确认 Machine 与 Optional Header Magic
3. 检查节数量、节表边界和对齐参数
4. 建立 RVA、VA、FOA 映射
5. 确认入口点所在节和节权限
6. 解析 Import、Export、TLS、Reloc、Exception、Resource
7. 检查 Load Config、Debug、Security 和 Overlay
8. 关注可写可执行节、高熵、异常入口点和极少导入
9. 在调试器中验证模块基址、IAT、TLS 和真实入口点
```

## 0x13 总结

PE 文件不是简单的机器码拼接，而是一份描述 Windows 如何构造进程映像的结构化文件。理解 PE 可以归纳为三个层次：

```text
第一层：DOS Header、NT Headers、Section Table 和节数据
第二层：FOA、RVA、VA 的地址映射
第三层：映射节、重定位、导入修复、TLS、异常和入口点执行
```

分析任何 PE 时，首先要确认自己面对的是磁盘布局还是内存布局。只要牢牢记住 `VA = ImageBase + RVA`，并在磁盘分析中正确完成 RVA 到 FOA 的转换，就能避免导入表、资源表、重定位表和入口点分析中的大量错误。

后续实践可以准备一个自编译的 x86 EXE、x64 EXE 和 DLL，分别记录 ImageBase、入口点、节权限、IAT、重定位和 TLS，再用 x64dbg 对照实际模块基址和内存内容。通过“字段—文件偏移—内存地址—加载行为”四者互相验证，才算真正掌握 PE 结构。

# 0x14 建立一份可复用的 PE 解析模型

逆向时不要把 PE 当成一组孤立结构体。更稳定的做法是建立四张表：文件范围表、节映射表、目录表和运行时地址表。每一次解析都记录字段名、原始偏移、原始值、换算后的 RVA/VA、所属节以及可信度。这样即使样本被加壳、改节名或破坏部分目录，也能快速判断是文件异常还是解析方式错误。

- 文件范围表：记录文件大小、头部边界、每个节的 Raw 范围、证书范围和 Overlay 范围。
- 节映射表：记录 VA 起点、RVA 起点、FOA 起点、VirtualSize、SizeOfRawData 和权限。
- 目录表：记录目录索引、RVA/FOA、Size、所属节、是否映射到内存。
- 运行时地址表：记录模块实际基址、入口点 VA、IAT 写入地址、TLS 回调 VA 和重定位 Delta。

## 14.1 一个最小样本的字段链

```text
文件偏移 0x00  -> DOS e_magic = 4D 5A
文件偏移 0x3C  -> e_lfanew = 0x80
文件偏移 0x80  -> PE\0\0
0x84            -> IMAGE_FILE_HEADER
0x98            -> IMAGE_OPTIONAL_HEADER
可选头之后       -> IMAGE_SECTION_HEADER[NumberOfSections]
节数据           -> 根据 VirtualAddress / PointerToRawData 建立映射
目录项           -> 再定位 Import、Reloc、TLS、Resource 等表
```

上面的链条表达的是解析依赖关系，而不是某个固定样本的绝对布局。e_lfanew、SizeOfOptionalHeader、NumberOfSections 和各节字段必须从当前文件读取，不能把示例中的偏移写死到工具中。

# 0x15 IMAGE_DOS_HEADER：字段级检查

- e_magic：必须为 IMAGE_DOS_SIGNATURE（0x5A4D），小端字节为 4D 5A。
- e_cblp、e_cp、e_cparhdr：属于 DOS 时代字段，现代 PE 分析通常用于完整性参考。
- e_lfarlc：指向 DOS 重定位表；它属于 DOS 兼容字段，不应与 PE 的 Base Relocation Directory 混淆。
- e_lfanew：文件偏移 0x3C 处的 4 字节值，必须同时满足非负、未溢出、落在文件范围内以及后续能读到 PE 签名。

```c
if (fileSize < sizeof(IMAGE_DOS_HEADER)) return BAD_FORMAT;
if (dos->e_magic != IMAGE_DOS_SIGNATURE) return BAD_FORMAT;
if (dos->e_lfanew < 0) return BAD_FORMAT;
if ((uint64_t)dos->e_lfanew + 4 > fileSize) return BAD_FORMAT;
if (memcmp(file + dos->e_lfanew, "PE\0\0", 4) != 0) return BAD_FORMAT;
```

# 0x16 COFF File Header：用属性判断样本

- Machine 与 Optional Header Magic 应相互吻合；例如 x86 常见 0x014C + PE32，x64 常见 0x8664 + PE32+。不吻合时要优先怀疑文件被构造、解析错位或工具显示错误。
- NumberOfSections 不只是遍历次数，还决定节表总长度。要检查节表起点加数量乘 IMAGE_SIZEOF_SECTION_HEADER 是否溢出。
- Characteristics 中 IMAGE_FILE_DLL、IMAGE_FILE_EXECUTABLE_IMAGE、IMAGE_FILE_RELOCS_STRIPPED 等标志可帮助解释加载方式，但不能代替实际行为观察。
- TimeDateStamp 适合做样本聚类线索，不适合单独作为编译时间、文件来源或家族归属的证据。

# 0x17 Optional Header：把“可选”拆成加载参数

Optional Header 的前半部分描述映像如何运行，后半部分的 DataDirectory 描述重要表在哪里。分析时建议将字段分成四组：入口与基址、对齐与大小、运行缓解、目录索引。

- 入口与基址：AddressOfEntryPoint、ImageBase、BaseOfCode。入口点是 RVA，必须结合实际模块基址换算成 VA。
- 对齐与大小：SectionAlignment、FileAlignment、SizeOfImage、SizeOfHeaders。磁盘对齐与内存对齐不能混用。
- 运行缓解：DllCharacteristics、Subsystem、MajorSubsystemVersion 等。标志只表示声明或兼容性，仍需在调试器中确认实际保护。
- 目录索引：NumberOfRvaAndSizes 与 DataDirectory 数组。目录数量不足时不能越界读取；目录的 Size 也必须参与边界检查。

## 17.1 PE32 与 PE32+ 的差异

```text
PE32  Magic = 0x10B
PE32+ Magic = 0x20B
PE32+ 没有 BaseOfData
PE32+ 的 ImageBase、SizeOfStackReserve、SizeOfHeapReserve 等字段为 64 位
重定位：x86 常见 IMAGE_REL_BASED_HIGHLOW，x64 常见 IMAGE_REL_BASED_DIR64
```

不要仅因为文件扩展名是 .exe 就按 32 位结构解析。正确顺序是先读取 Magic 和 Machine，再选择对应的 IMAGE_NT_HEADERS32 或 IMAGE_NT_HEADERS64。

# 0x18 节映射：把磁盘与内存分开

每个 IMAGE_SECTION_HEADER 至少要回答五个问题：节在文件哪里、节在内存哪里、文件有多少字节、内存需要多少字节、哪些页权限。VirtualSize 大于 SizeOfRawData 时，超出的部分通常由加载器零填充；它存在于进程内存，却没有对应文件字节。

```text
节的文件范围： [PointerToRawData, PointerToRawData + SizeOfRawData)
节的内存范围： [VirtualAddress, VirtualAddress + max(VirtualSize, SizeOfRawData))
RVA -> FOA：PointerToRawData + (RVA - VirtualAddress)
如果 RVA 落在零填充尾部：有内存地址，但没有合法 FOA
```

- 节名只是提示：恶意样本可以把代码放进 .data，把资源放进 .text，也可以把多个节合并。
- Characteristics 中 EXECUTE、READ、WRITE 的组合比节名更值得优先检查。
- 可写可执行节不等于恶意，但它是自修改、解密代码、JIT 或壳代码的重要线索。
- SizeOfRawData 应按 FileAlignment 解释；VirtualSize 应按内存映射解释，不能用一个替代另一个。

# 0x19 Data Directory：每一项都要单独解释

Data Directory 不是“目录内容”，而是指向其他结构的索引。解析器应先根据索引判断该项是否存在，再根据目录类型决定 RVA/FOA 规则，最后验证结构内部的指针和计数。

- Export：导出函数地址、名称和序号。函数 RVA 落在导出目录范围内时，可能是转发导出。
- Import：导入 DLL 与函数引用。FirstThunk 在加载后通常变成 IAT，内存分析与磁盘分析的含义不同。
- Resource：资源目录是树，不要把资源数据当成一个连续表；先遍历目录项，再定位语言层和数据项。
- Exception：x64 常见 RUNTIME_FUNCTION 表，可辅助函数边界和栈展开分析。
- Security：VirtualAddress 按文件偏移处理，通常不映射进进程内存，是最容易误用的目录。
- Debug：可能含 CodeView、PDB 路径、GUID 和 Age。PDB 路径是环境线索，不等于样本行为结论。
- TLS：目录、回调数组和 TLS 模板。TLS 回调可能早于普通入口点执行。
- Load Config：安全 Cookie、CFG 相关表以及其他加载配置，必须尊重目录 Size 和结构版本。

# 0x1A 导入解析实战：从 DLL 到 API 调用

导入分析的目标不是简单列出 DLL 名称，而是回答“程序依赖什么能力、这些能力如何被调用、导入是否被隐藏”。建议把静态导入、延迟导入、运行时解析和 API Set 分开记录。

```text
IMAGE_IMPORT_DESCRIPTOR
  OriginalFirstThunk -> IMAGE_THUNK_DATA[]（名称/序号）
  Name               -> "KERNEL32.dll"
  FirstThunk         -> IAT

加载前：IAT 中通常还是导入引用
加载后：IAT 中通常被写入目标函数 VA
```

- 按名称导入：Thunk 指向 IMAGE_IMPORT_BY_NAME，先读取 Hint，再读取 ASCII 函数名。
- 按序号导入：Thunk 最高标志位表示 ordinal，不能把剩余值当作字符串 RVA。
- OriginalFirstThunk 为 0：不能立即判定导入损坏，应结合 FirstThunk、磁盘/内存状态和加载结果分析。
- GetProcAddress、LdrGetProcedureAddress、哈希解析和手动遍历导出表会绕过常规静态导入。
- IAT 断点适合确认 API 真实调用；如果壳在运行时重建 IAT，应先找到解密或修复阶段。

# 0x1B 重定位：从 Delta 到具体地址

重定位不是“修复所有指针”，而是按照重定位块声明的类型和页内偏移，修正那些需要随模块基址变化的绝对地址。先计算 Delta，再逐块遍历；遇到 ABSOLUTE 项只跳过，不要把它当作待修复地址。

```text
Delta = ActualImageBase - OptionalHeader.ImageBase
Block.VirtualAddress = 页 RVA
Entry.Type = Entry >> 12
Entry.Offset = Entry & 0x0FFF
PatchVA = ActualImageBase + Block.VirtualAddress + Entry.Offset
若 Type == DIR64：*(uint64_t*)PatchVA += Delta
```

# 0x1C TLS 与真实入口点

当样本存在 TLS 回调时，“入口点”至少有三个概念：Optional Header 的 AddressOfEntryPoint、TLS 回调地址、程序最终进入的业务入口。调试时应在模块加载、TLS 回调和 OEP 三个阶段分别记录寄存器、内存权限和控制流。

- 先从 TLS Directory 找 AddressOfCallBacks，再按指针宽度读取以 NULL 结尾的回调数组。
- 确认回调地址属于当前模块的可执行范围，防止把损坏指针或外部模块地址误判为 TLS。
- 观察回调是否解密代码、修改 IAT、设置断点检测或改变节权限。
- TLS 回调执行完并不代表程序已经进入业务逻辑，仍需继续跟踪普通入口点和后续跳转。

# 0x1D 用 Python 做第一轮结构化检查

```python
import pefile

pe = pefile.PE("sample.exe", fast_load=False)
print(hex(pe.OPTIONAL_HEADER.ImageBase))
print(hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint))
print("EP VA:", hex(pe.OPTIONAL_HEADER.ImageBase + pe.OPTIONAL_HEADER.AddressOfEntryPoint))
for s in pe.sections:
    name = s.Name.rstrip(b"\0").decode(errors="replace")
    print(name, hex(s.VirtualAddress), hex(s.Misc_VirtualSize),
          hex(s.PointerToRawData), hex(s.SizeOfRawData), hex(s.Characteristics))
for entry in pe.DIRECTORY_ENTRY_IMPORT:
    print(entry.dll.decode(errors="replace"))
    for imp in entry.imports:
        print("  ", imp.name, hex(imp.address) if imp.address else None)
```

自动化脚本的价值在于批量记录和对比，不在于替代人工判断。建议把脚本输出保存为 JSON，并保留文件 SHA-256、工具版本和样本采集时间。

# 0x1E 调试器验证路径（以 x64dbg 为例）

- 模块载入后记录实际 ImageBase，与 Optional Header.ImageBase 比较，计算是否发生重定位。
- 在模块入口点、TLS 回调和疑似 OEP 处分别下断点，观察执行顺序。
- 跟随 IAT 中的 API 地址，确认调用参数和调用约定；不要只依据函数名推断行为。
- 在 VirtualProtect、NtProtectVirtualMemory、LoadLibrary、GetProcAddress 等位置记录权限变化和动态解析。
- 对照内存窗口与文件窗口：内存中的节可能已完成重定位、IAT 修复或解密，不能直接与磁盘字节逐字比较。

# 0x1F 一个完整 PE 样本的复盘模板

```text
样本：sample.exe
SHA-256：...
架构：x64 / PE32+
ImageBase：0x140000000
EntryPoint RVA：0x12340
EntryPoint VA：0x140012340
节：.text RX、.rdata R、.data RW、.rsrc R、.reloc R
导入：KERNEL32.dll / USER32.dll / ...
TLS：存在 / 不存在；回调：...
重定位：存在 / 被剥离；实际 Delta：...
异常：.pdata 范围 ...
签名：存在 / 不存在；Overlay：大小 ...
结论：静态证据 + 动态证据 + 未确认项
```

复盘报告要把“观察到的事实”和“基于事实的推断”分开。例如“入口点位于 .text”是事实；“样本没有加壳”则是推断，需要结合导入、熵、控制流和动态行为说明证据。

# 0x20 易错点升级版：看到异常先定位层次

- 文件层异常：签名、偏移、大小、对齐、节边界或目录范围不一致。
- 映射层异常：RVA 无法映射、节权限与内容不匹配、零填充区域被当成文件数据。
- 加载层异常：重定位失败、导入解析失败、TLS 回调先于入口点、IAT 被覆盖。
- 行为层异常：入口点只是壳代码、真实 API 通过哈希解析、代码运行后才生成。

# 0x21 结语：用 PE 形成逆向知识体系的样板

PE 这一章适合作为整个逆向笔记的样板，因为它同时训练格式阅读、地址换算、边界检查、工具使用、静态推断和动态验证。后续写汇编、Windows 原理、静态分析或恶意代码分析时，也可以沿用同一结构：先定义对象，再说明字段，再给出转换关系，最后用一个可复现的样本和验证步骤收束。

# 0x22 看雪资料索引与交叉校验

本章的深化部分参考了看雪安全社区中多篇 PE 主题文章，并以 Windows PE/COFF 字段定义和实际加载行为进行交叉校验。论坛文章适合学习分析思路与实战路径，但个别旧帖或个人笔记可能存在表述偏差，因此结构大小、结束条件和地址规则应以当前样本、SDK 结构定义及调试结果为准。

- 《打造自己的PE解析器》（thread-252795）：重点参考 PE 解析器的整体实现顺序、RVA/FOA 转换、导入表、绑定导入和资源树的逐层定位思路。
- 《归纳PE结构基础知识，顺便手撕个PE》（thread-270210）：重点参考从 DOS 头、NT 头、可选头到节表的手工定位流程，并对帖中结论进行边界与规范校验。
- 《一文读懂PE文件签名并手工验证签名有效性》（thread-272464）：重点参考 Security Directory、WIN_CERTIFICATE、PKCS#7 与 Authenticode 数据的文件偏移特性。
- 《UPack壳的PE头部分析》（thread-288481）：重点参考壳对 e_lfanew、SizeOfOptionalHeader 和头部重叠的利用，以及“系统能加载但分析器可能误判”的对抗视角。
- 《游戏逆向中常用的Hook技术》（thread-290783）：重点参考 IAT 在文件状态与加载后状态的差异，以及 IAT Hook 的结构基础。

建议后续实践时为每个知识点保留“三证”：结构字段截图或十六进制偏移、解析脚本输出、调试器中的运行时地址。三者一致时再把结论写入复盘；不一致时记录差异，而不是强行套用标准结构。
