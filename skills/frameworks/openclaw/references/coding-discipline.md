# Karpathy Coding Principles（L1 OpenClaw）

> Adapted from [andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills)

**Tradeoff:** 偏谨慎； trivial 改动（typo、单行修复）可酌情放宽。

## 1. Think Before Coding

- 显式陈述假设；不确定则问
- 多义方案并列，不静默选一
- 有更简方案则提出；不清楚则停下

## 2. Simplicity First

- 不做超出需求的 feature
- 单次使用的代码不抽象
- 200 行能 50 行解决则重写

## 3. Surgical Changes

- 不改相邻无关代码
- diff 最小，每行变更可追溯任务
- 仅删除**你的变更**导致的 dead import

## 4. Goal-Driven Execution

| 指令 | 转为可验证目标 |
|------|----------------|
| Add validation | 写失败测试 → 使通过 |
| Fix bug | 复现测试 → 使通过 |
| Refactor X | 前后测试均绿 |

多步任务列 checkpoint：`[Step] → verify: [check]`
