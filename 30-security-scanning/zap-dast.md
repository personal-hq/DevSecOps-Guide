# ZAP DAST

## 与前三个工具的根本区别

gitleaks / trivy / semgrep 扫的是仓库内容本身，任何仓库、任何时候都能跑。ZAP 不一样，它是 **DAST**（Dynamic Application Security Testing）——测的是服务跑起来之后的行为，前提是要有一个能接收 HTTP 请求的服务。**纯库、没有对外 HTTP 服务的仓库，ZAP 的三种扫描方式都用不上。**

## 三个打包脚本的实测差异

来自各脚本 `-h` 输出，不是记忆：

| | spider 默认时限 | `-a` 包含的规则 | 性质 |
|---|---|---|---|
| baseline | **1 分钟** | alpha **被动**规则 | 只被动观察 |
| full-scan | **无限制** | alpha **主动**+被动 | **真的发起攻击** |
| api-scan | 不爬，读 spec | alpha 被动 | 按 OpenAPI/SOAP/GraphQL 定向 |

## 触发矩阵

- **baseline**——应该自动化：部署 staging 后跑一次，或者定时
- **full-scan**——只能定时或手动：spider 无上限、真的发起攻击、会往表单里灌数据，**绝不能指向生产**
- **api-scan**——有 spec 时比 baseline 更准，按接口定向而不是靠爬虫发现

## Forgejo 触发器支持（全部实测）

| 触发器 | 支持情况 |
|---|---|
| `workflow_dispatch` + inputs | ✅ 支持——派发 API 返回 204，产生 `event=workflow_dispatch` 的运行 |
| `schedule` | ✅ 支持——`action_schedule_spec` 表登记了 cron 和 next 时间戳 |
| `workflow_run` | ❌ **实测未触发**——探针写了三种 workflow 名字、两种 types，之后跑两轮 ci，17 次运行 0 个该事件 |

**所以"部署成功后自动扫"不能用 `workflow_run`。** 替代方案三选一：

1. 作为部署 workflow 的最后一个 job（`needs: deploy`）——**推荐**，不需要跨 workflow 通信
2. 部署脚本结束时调 dispatch API
3. schedule 兜底，不追求"部署后立刻扫"

## Automation Framework（官方主推方向）

用 `-autorun <plan.yaml>` 跑一个声明式的 plan；`-autogenmin`/`-autogenmax`/`-autogenconf` 生成模板——这四个 flag 实测存在。三个打包脚本本质上是预制好的 plan（例如 `api-scan` 就是一个带 `openapi` job 的 plan）。

比命令行强在四处：

**1. `tests:` 断言——最重要。** `spider` job 可以挂一条统计断言：

```yaml
jobs:
  - type: spider
    parameters:
      maxDuration: 5
    tests:
      - name: "爬到的 URL 数量不能太少"
        type: stats
        statistic: "automation.spider.urls.added"
        operator: ">="
        value: 20
        onFail: error
```

这是 DAST 版的"已知坏样本"（参见 [00-principles.md](../00-principles.md) 第一条）。ZAP 最典型的失效是登录没成功、只爬到登录页、然后给一份很干净的报告——干净是因为什么都没扫到，不是因为没洞。用爬取 URL 数当哨兵，失效会主动报错，而不是安静地产出一份看起来正常的报告。`activeScan`/`passiveScan-wait` 还能断言特定告警的有无：

```yaml
tests:
  - name: "已修复的越权漏洞不允许回归"
    type: alert
    scanRuleId: <规则 ID>
    action: passIfAbsent
    onFail: error
```

这样可以锁定"已经修复的洞不许回归"。

**2. `alertFilter` 比 `.zap/rules.tsv` 精细得多。** 按 url/parameter/evidence 加正则匹配，把某条告警改判成 `False Positive`，可以限定只在某个路径下豁免：

```yaml
- type: alertFilter
  parameters:
    deleteGlobalAlerts: false
  alertFilters:
    - ruleId: <规则 ID>
      newRisk: "False Positive"
      url: "https://staging.example.internal/health.*"
      urlRegex: true
```

做基线分诊应该用这个，不要用命令行脚本自带的规则文件。

**3. `activeScan-policy` 让主动扫描不再是全有全无。** 按 `alertTags` 挑规则、按规则单独设 strength/threshold，可以做成分钟级的定向扫描：

```yaml
- type: activeScan
  parameters:
    policy: "injection-only"

- type: activeScan-policy
  parameters:
    name: "injection-only"
  policyDefinition:
    defaultThreshold: "off"
    rules:
      - id: <规则 ID>   # 例如 SQL 注入类规则
        threshold: high
        strength: high
      - id: <规则 ID>   # 例如 XSS 类规则
        threshold: high
        strength: high
```

**这纠正的是一个概念混淆**：`full-scan.py`（无 spider 上限 + 全量主动规则）不能进门禁，
不等于"任何主动扫描都不能限时"。`activeScan-policy` 让主动扫描不再是全有全无。

**但它仍然不进 PR 合入门。两个理由，都是硬的：**

1. **冷 PR 没有活 URL。** DAST 打的是跑起来的服务。一个还没被部署到任何地方的 PR，
   物理上没有扫描目标。要在 PR 上跑 DAST，前提是**每个 PR 都有独立预览环境**——
   那是另一整套基础设施，**我们没有，也没验证过**。
2. **超 PR 预算。** [`05-architecture.md`](../05-architecture.md) 定的是 PR CI
   **合计** ≤5 分钟（semgrep + trivy lockfile + 单测）。再加 5 分钟定向主动扫是
   翻倍，不是"踩线"。同一份文档里"慢的东西不进 PR 门禁"和"限时 5 分钟可以进门禁"
   自相矛盾——**以前者为准**。

**限时定向计划的正确挂载点是"预发已经起来"之后的 job，挡的是晋升生产，不是合并。**
这也是公司方案的规定（不挡冷 PR；`activeScan` 不进组织级模板）。

**4. 其它 job 类型**：`openapi`/`graphql`/`soap`/`postman`/`har` 导入现成接口定义；`spiderAjax`/`spiderClient`——现代 SPA 用传统 spider 爬不动，需要执行 JS 才能发现路由；`exitStatus`（CI 门禁接口，按 `errorLevel`/`warnLevel` 决定退出码）；`env.parameters.failOnWarning`/`continueOnFailure`（plan 级别的失败策略，决定一个 job 失败要不要影响后续 job）。

## 最小可用 plan

```yaml
env:
  contexts:
    - name: "app"
      urls:
        - "https://staging.example.internal"

jobs:
  - type: spider
    parameters:
      context: "app"
      url: "https://staging.example.internal"
      maxDuration: 5
    tests:
      - name: "爬取 URL 数量哨兵"
        type: stats
        statistic: "automation.spider.urls.added"
        operator: ">="
        value: 20
        onFail: error

  - type: passiveScan-wait
    parameters:
      maxDuration: 5

  - type: report
    parameters:
      template: "risk-confidence-html"
      reportDir: "/zap/wrk"
      reportFile: "zap-report"

  - type: exitStatus
    parameters:
      errorLevel: "High"
```

**没有那个 `tests` 哨兵，后面所有配置都可能是在给一份空扫描做精装修。** 报告好看不代表扫到了东西。

## 三个实操坑

1. 部署后先 curl 健康检查，确认服务真的起来了，再启动 ZAP——服务没起来 ZAP 会对着一个连接失败的目标跑完整个流程，产出一份没有意义的"干净"报告
2. 不配认证等于白扫——ZAP 只能看到登录页，报告"很干净"是因为什么都没扫到，不是因为没洞
3. 要能当门禁，必须先做基线分诊（用 `alertFilter` 标掉已知的误报/可接受项），不然第一次跑就会因为一堆噪音把门禁堵死

## 本环境特有的坑

ZAP 容器要能打到目标 URL。runner 在 compose 网络里，job 容器却在 DinD 的独立网桥上——和 `actions/checkout` 解析不到 forgejo 是同一类问题，修法参见 [20-ci-cd/README.md](../20-ci-cd/README.md)"已知的 CI 网络坑"一节。

---

## 实做记录：baseline 的退出码不能当判据（2026-08-29）

对一个**故意不设任何安全响应头**的 Express 应用跑 `zap-baseline.py`，汇总行是：

```
FAIL-NEW: 0   FAIL-INPROG: 0   WARN-NEW: 11   WARN-INPROG: 0   INFO: 0   IGNORE: 0   PASS: 56
```

命中的正是种下的那些：`Cookie No HttpOnly ×2`、`Cookie without SameSite ×2`、
`Missing Anti-clickjacking ×3`、`X-Content-Type-Options Missing ×3`、`CSP Not Set ×3`，
外加 `X-Powered-By` 泄露、`Permissions-Policy`、`COEP`。

**但它们全是 WARN，没有一条 FAIL** ——只看退出码，这一步是"过"的。
一个连 CSP、X-Frame-Options、HttpOnly 都没有的应用，baseline 默认判定不红。

所以门禁不能只接退出码，要么用 AF plan 的 `exitStatus.warnLevel`，要么在 job 里自己断言：

```bash
for rule in "Content Security Policy" "Anti-clickjacking" "X-Content-Type-Options"; do
  grep -q "$rule" /tmp/zap.txt || { echo "没命中 $rule —— ZAP 没真打到应用"; exit 1; }
done
```

**这个断言是反向的**：应用故意有这些问题，**扫不出来才说明扫描器坏了**。
这就是 [00-principles](../00-principles.md) 第 1 条在 DAST 上的具体形态——
canary 不一定是一个仓库，也可以是"预期必须命中的一组规则"。
