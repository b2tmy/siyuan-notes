---
title: 07 第七章 构建你的Agent框架
date: 2026-10-08T19:56:25+08:00
lastmod: 2026-10-08T19:56:25+08:00
---

# 07 第七章 构建你的Agent框架

# 第七章 构建你的Agent框架｜自建框架：先固定接口，再扩展能力

> 看雪式技术复盘：先找入口，沿调用链追状态，用反例验证分支，最后落到自己的实现。本文不是原文搬运，也不把教材展示日志当成本次实测。

## 0x00 前言：这一章到底解决什么

这是后续自己写 Agent 的主干章节。不要从复制所有类开始，而应从“一次请求如何经过模型、工具和状态返回结果”反推最小接口。教材给出的统一抽象值得借鉴，演示代码的默认行为则要逐项验证。

## 0x01 知识拆解：原理、接口与数据

### 1. 模型适配器隔离供应商细节

HelloAgentsLLM 把模型名、凭证、服务地址和调用方式集中封装。自动识别方便体验，但多个环境变量同时存在时可能选错后端。我们的规则是显式配置优先，记录最终解析出的 provider、model 和 endpoint 类型，不记录密钥。

兼容同类 HTTP 接口不等于流式事件、工具调用、结构化输出和错误码完全相同，适配器需要能力声明和契约测试。

### 2. Message、Config、Agent 的职责

Message 是内部规范的数据结构，带角色、内容、时间与元数据；发送前转成服务所需格式。Config 管配置与预算。Agent 定义 run 入口及状态生命周期，具体范式实现决策方式。

别把“对话列表”当全部状态。运行至少需要 run_id、status、step、observations、pending_calls、usage 和终止原因。这样才有恢复、审计和评估的基础。

### 3. 四种范式共享底座

SimpleAgent 做基础交互，ReActAgent 循环使用观察，ReflectionAgent 加反馈回路，PlanAndSolveAgent 拆规划与执行。FunctionCallAgent 把动作表达交给结构化工具协议。框架抽象的目标是共享验证和执行逻辑，而不是每个 Agent 各维护一份脆弱解析器。

### 4. ToolRegistry 是执行入口

工具要有稳定名称、说明、输入 schema 和统一结果。注册同名工具时，教材演示以警告后覆盖处理；我们的最小实验改为拒绝重复，避免一个名称在同次运行中指向不同函数。

工具返回建议是 {ok,data,error,source,latency}，而非一律转成长字符串。对于写操作还需 operation_id、确认阶段和幂等信息。模型可以请求动作，运行层决定动作能否执行。

### 5. 计算器与搜索体现两类边界

教材计算器使用 AST 白名单而非直接执行表达式，这是值得保留的方向。不过 Constant 需要验证数值类型，未知节点应明确报错，一元负号、除零、深层表达式和大小上限都要测试。

多源搜索应统一结果字段并记录实际 backend。备用源成功不能掩盖原源失败；所有来源都失败时，返回失败对象而不是生成一段像搜索结果的文本。

### 6. 工具链与异步

依赖上一步输出的工具串行；独立工具可并发，但每个结果必须关联 call_id。取消、超时、清理和并发额度由执行层处理。

## 0x02 调用链：从输入追到结果

```text
Agent.run → Context → ModelAdapter → Action schema → ToolRegistry → Executor → ToolResult → State → Finish。
```

调试顺序：先确认输入与配置，再查看关键状态，核对实际工具结果，最后检查终止和输出。将“模型判断有误”和“执行器实现有误”分开记录，避免通过改 Prompt 掩盖程序缺陷。

## 0x03 阅读与复现方法

本章先读原文对应节，再看关键对象与代码边界，最后用下方离线实验验证一个最小机制。真实系统的复现需要固定依赖、配置与输入；与教材不同的补充设计均在本文按工程分析展开，不冒充原作者实现。

## 0x04 最小实验：先用确定性输入验证机制

实验环境：本机 Python 标准库，无外部模型与服务调用。以下为原创教学实验，并非直接运行教材完整项目。实验集合保存于 ​`E:\my_agent\agent_learning\labs\offline_labs.py`。

```python
import ast
import math
import re

def ch07():
    registry = {}
    def register(name, fn):
        if name in registry:
            raise ValueError('duplicate_tool')
        registry[name] = fn
    register('add', lambda a, b: a+b)
    try:
        register('add', lambda a, b: 0)
    except ValueError as e:
        error = str(e)
    result = registry['add'](2, 3)
    assert result == 5 and error == 'duplicate_tool'
    return {'result': result, 'duplicate': error, 'tool_count': len(registry)}

print(ch07())
```

运行命令（PowerShell）：

```powershell
python -X utf8 "E:\my_agent\agent_learning\labs\offline_labs.py"
```

本章实际输出（JSON 记录）：

```json
{
  "result": 5,
  "duplicate": "duplicate_tool",
  "tool_count": 1
}
```

实验集合结果：​`CHAPTERS=15 PASS=15 FAIL=0 MODE=OFFLINE`​，进程退出码 ​`0`。这些断言只验证上述机制和样例，不代表真实 LLM 能力、外部服务可用性或完整产品上线验收。

## 0x05 易错点与排查清单

- 继承框架后重写私有方法，却没有固定版本与契约测试。
- 所有异常都返回“计算失败”，导致上层失去诊断信息。
- 把工具调用字符串解析成功等同于业务执行成功。

## 0x06 落到我们自己的 Agent

目录先分 core、models、tools、memory、evaluation；统一 Action、ToolResult、RunState 三个契约后，只接 read_document、search_notes、draft_note 三个工具。

## 0x07 自测与参考思路

**问题 1：为什么同名注册默认报错？**

参考思路：让名称与实现稳定绑定，避免悄悄覆盖使回放结果变化。

**问题 2：什么时候增加接口？**

参考思路：出现第二个真实实现或明确测试需求时，避免为假想扩展制造抽象。

**问题 3：Function Calling 后还要验证吗？**

参考思路：要，结构格式约束不能代替业务范围、权限和结果检查。

## 0x08 原文定位与复盘入口

本地教材：​`C:\Users\Lenovo\Downloads\hello-agents-main\hello-agents-main\docs\chapter7\第七章 构建你的Agent框架.md`

SHA-256：​`4c06cb8aa0adbe1bbe3c88e817d509e4b30cd9190e849bdc54c4f86e13ba8c48`

- `7.1 框架整体架构设计`：原文第 7 行起。
- `7.2 HelloAgentsLLM扩展`：原文第 154 行起。
- `7.3 框架接口实现`：原文第 459 行起。
- `7.4 Agent范式的框架化实现`：原文第 605 行起。
- `7.5 工具系统`：原文第 1349 行起。
- `7.6 本章小结`：原文第 2146 行起。

内容归属：教材框架、案例及术语来自 Datawhale Hello-Agents；本笔记的调用链拆解、反例、项目决策与离线实验是整理补充。保留教材 CC BY-NC-SA 4.0 许可说明。日期：2026-10-08。

阅读状态：已完成本章资料整理、关键代码检查与对应离线机制实验；涉及真实模型、外部 API、平台部署、GPU 训练或正式基准的联调尚未执行。原文中的版本与演示结果均属于教材基线。
