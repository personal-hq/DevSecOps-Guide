# SAST 引擎选型：CodeQL / Semgrep / Opengrep

一次实测对比。结论先行：

- **CodeQL 在私有代码库上不能免费用**——不是"商用/非商用"之分，是"是不是开源代码库"之分
- **Opengrep 在我们当前用法下与 Semgrep 结果完全一致**，现在换没有收益
- 但**如果将来要用跨文件污点分析，Opengrep 是许可证干净的候选**，Semgrep 那部分已进付费墙

---

## 一、CodeQL：许可证按「是否开源」划线，不按「是否商用」

常见误解是"内部用不算商用所以能用"。**这个 license 不是按商用划线的。**

`github/codeql-cli-binaries` 的 LICENSE.md 明确禁止：

> "To otherwise or in any other context use the Software in connection with
> **any codebase that is not an Open Source Codebase**
> (e.g., **code in a private repo in GitHub**)."

它直接把「私有仓库里的代码」写成反例。免费允许的只有三类：

1. 学术研究
2. 演示该软件本身
3. 测试以 OSI 许可证发布的 CodeQL 查询是否仍能发现漏洞

外加：托管在 GitHub.com 上的**开源**代码库可做分析与 CI/CD。

唯一豁免：

> "if your use of the Software is under a **paid customer license for GitHub Advanced Security**,
> the restrictions … do not apply."

**所以：内部公司代码 = 私有仓库 = 不是 Open Source Codebase = 需要 GHAS 付费。**
自建 Forgejo 的情况下，连"GitHub.com 上的开源仓库"这条例外都不适用。

> ⚠️ 另注意仓库许可证标签会误导：`github/codeql` 标 MIT，但**实际使用受上述独立条款约束**。
> 这是典型的「仓库许可证 ≠ 你能拿它做什么」，见 [02-tool-landscape.md](../02-tool-landscape.md)。

（以上是对许可证文本的直接引用，不构成法律意见；具体适用请自行判断。）

---

## 二、Semgrep 的许可证故事有两层

只看 `semgrep/semgrep` 的 LGPL-2.1 标签会得出错误结论：**仓库许可证没变，但能力被移走了。**

2024-12 Semgrep 把跨文件污点分析等能力移进付费平台。2025-01 多家安全厂商
（Aikido、Amplify、Endor Labs、Kodem、Orca Security）把功能完整的最后一版
fork 成 **Opengrep**。其 README 原文：

> "Opengrep was created when Semgrep moved critical features behind a commercial licence."

- fork 点：**Semgrep v1.100.0**
- 许可证：**LGPL 2.1**
- 我们流水线跑的是 `semgrep==1.175.0`，**在 fork 点之后**

---

## 三、实测对比（2026-08-29 实做）

环境：`debian:trixie-slim` 容器；**opengrep 1.29.0**（官方 install.sh 安装）
vs **semgrep 1.175.0**（pip）；两者同样 `--config p/default`，扫同一份代码。
观测日 **2026-08-29**。

> ⚠️ **下面的数字是那一天、那两个版本、那一版 `p/default` 的观测记录，不是不变量。**
> 你照「复现方法」跑出来的数**大概率和这里不同**——引擎在更新，`p/default` 是在线
> 规则库也在变。**那不是复现失败。**
>
> 这几张表要证明的是**结论**，不是计数：① 我们实际用法下两个引擎结果一致
> ② 跨文件样本上两者都不报。重跑时要看的是这两句还成不成立，
> 不是"我也应该得到 3"。

### 测试 1 · 单文件模式匹配（我们当前的实际用法）

样本来自 canary 仓库：假 AWS 凭据 + `exec("ls " + userInput)` 命令注入。

| 引擎 | 发现数 | 结果 |
|---|---|---|
| semgrep 1.175.0 | 3 | `detected-aws-access-key-id-value` / `detected-aws-secret-access-key` / `detect-child-process` |
| opengrep 1.29.0 | 3 | **完全相同**——同样位置、同样规则 ID |

**→ 当前用法下两者无差别。**

### 测试 2 · 跨文件污点（专门构造，用来检验付费墙是否影响我们）

只做测试 1 是不够的——**被移进付费的恰恰是跨文件分析，而测试 1 的样本不触发它**。
用不触发该能力的样本去测它，等于没测（见 [00-principles.md](../00-principles.md) 第 1 条）。

构造样本：`source.js` 里 `req.query.host` 进入 → 跨文件调用 → `sink.js` 里 `exec()`。

| 引擎 | 结果 |
|---|---|
| semgrep | 2 处，**均为模式匹配**，未追踪跨文件污点流 |
| opengrep | 2 处，**同上，也未追踪** |

**两者都没报出真正的跨文件注入。**

### 测试 3 · 能力开关（帮助文本实查）

| 引擎 | 相关 flag | 是否有付费门 |
|---|---|---|
| semgrep OSS | `--pro`、`--pro-intrafile`、`--interfile-timeout` | ✅ 明写 **"Requires Semgrep Pro Engine"**（单独安装的二进制 + 登录） |
| opengrep | `--dataflow-traces`、`--guarded-taint-signatures`，帮助里提到 interfile / deep preprocessor | ❌ 无付费门提示 |

### 顺带发现：CLI 不是 100% 兼容

`opengrep scan --metrics=off` 报 `unknown option '--metrics'`——Opengrep 移除了遥测开关。
**迁移时不能假设参数逐一对应。**

---

## 四、已确立与未确立的

**已确立：**
1. Opengrep 安装干净、可用、接受 `--config p/default` 在线规则库语法
2. 在我们**实际使用的场景**下，两个引擎结果逐条一致
3. 跨文件样本上两者都不报——说明我们**目前没有碰到付费墙**
4. Semgrep 的跨文件能力明确需要 Pro Engine，Opengrep 的对应 flag 无付费门

**未确立（不要当成结论）：**
- **Opengrep 是否真的能做跨文件污点分析尚未证明。** `p/default` 规则集里没有跨文件污点规则，
  所以测试 2 无法区分"引擎不支持"和"规则集不含"。要证明需要一条专门做跨文件追踪的规则。

---

## 五、结论与建议

| 问题 | 答案 |
|---|---|
| CodeQL 能当终审门禁吗 | ❌ 私有代码库上需 GHAS 付费 |
| 现在该换 Opengrep 吗 | ❌ **不该**。当前用法下零收益，还要承担年轻 fork 的长期维护风险 |
| 那记录它做什么 | 将来要用跨文件分析时，它是许可证干净的候选，届时**必须先用专门规则验证其跨文件能力** |

**要"语义级终审门禁"的现实选项：**

| 选项 | 许可证 | 备注 |
|---|---|---|
| Opengrep | LGPL-2.1 | 需先验证跨文件能力 |
| Semgrep + Pro Engine | 商业 | 单独二进制 + 登录 |
| GHAS（含 CodeQL） | 商业 | 想要 CodeQL 只此一条 |
| SonarQube | ⚠️ 主仓 LGPL-3.0，但**语言分析器插件已改非 OSI 许可** | 分析器才是干活的那部分 |

---

## 复现方法

**两边都装当前最新**——扫描器钉旧版本是反效果的，规则和引擎修复都在新版里。
代价是你复现不出上面那几个计数（见上方警告），所以判定标准不是数字相等，
是**两个引擎的发现集合是否仍然逐条一致**。

```bash
# Opengrep（装 latest）
curl -fsSL https://raw.githubusercontent.com/opengrep/opengrep/main/install.sh | bash
export PATH="$HOME/.opengrep/cli/latest:$PATH"

# Semgrep（装 latest）
pip install -U semgrep

# 先把版本记下来——没有这两行，你的结果不能当证据
opengrep --version; semgrep --version

# 扫同一份代码
opengrep scan --config p/default --json --quiet <目录> > og.json
semgrep scan --config p/default --json --quiet --metrics=off <目录> > sg.json

# 判定：按 (path, line, check_id) 取集合差，空集 = 结论仍成立
```

差集非空说明两个引擎在你的代码上**已经不等价了**——那才是需要重新决策的信号，
把新的版本号和差异写下来，替换掉上面那张表，别在旁边并列两组数。
