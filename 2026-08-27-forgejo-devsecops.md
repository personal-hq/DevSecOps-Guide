# Forgejo 内部 DevSecOps 方案

| 项 | 内容 |
|---|---|
| 读者 | 研发负责人、平台/SRE、安全、合规 |
| 场景 | 公司自建 Git 协作 + CI/CD + 供应链安全 |
| 覆盖 | 规模两档：**S 中小 / L 大型**。入口两种：**N 内网或零信任** / **P 公网须登录**。正交，共四格 |
| 共同点 | 两种入口都 **禁止匿名**：关闭注册、未登录看不到仓库；不是公开 forge |
| 基线版本（2026-08-29 核实） | **Forgejo 16**（当前补丁 **16.0.3**，[releases](https://forgejo.org/releases/)）。能力与引用按 **16** 写。补丁跟 16.0.x；下一稳定大版本发布后预发验证再升。钉 digest，不用浮动 `latest`，不回退 15 |
| Runner | 与 **16** 配套，当前 **13.0.0**。13 含破坏性 Actions 变更；禁止与 12.x 混跑；升 17 时 Runner 同次升 |
| 扫描栈 | **Gitleaks + Semgrep + Trivy + Renovate + ZAP**（外加 Cosign / syft，不进合并门） |
| 文档性质 | 架构与落地规格，不是安装手册、不是 POC |

---

## 1. 结论

**内部 DevSecOps 的控制面用 Forgejo，安全能力用「强制点 + 现成扫描器」接进 Actions，不要等 Forgejo 长出 GitHub Advanced Security。**

一句话分工：

- **Forgejo**：身份入口、源码、评审、Actions 调度、包仓库、审计线索的一半。
- **Runner 池**：按信任分区执行代码（这是整个方案最容易翻车的地方）。
- **扫描与签发**：Gitleaks（密钥）+ Semgrep（SAST）+ Trivy（SCA/镜像/IaC）+ Renovate（依赖 PR）+ ZAP（DAST，打已部署环境）+ Cosign（签名）。平台只编排和卡门，不自研扫描器。
- **部署**：GitOps（Argo CD / Flux）或 Actions 用 OIDC 换短凭证；生产凭据不进 Forgejo。
- **入口两种，都要能落地**：
  - **N · 内网或零信任**：公司网 / VPN / ZTNA（IAP、Cloudflare Access、Tailscale 等）才能摸到 443。网络是第一道门。
  - **P · 公网须登录**：443 在公网，但未登录等于没有这个站。`REQUIRE_SIGNIN_VIEW` + 关注册 + SSO/2FA。
- 两种都不是公开 forge：无匿名浏览、无匿名 clone、无自助注册。规模（S/L）和入口（N/P）分开选，不要绑死。

中小企业把同一张图收成「单机房 + 两个 Runner + 合并前门禁」。  
大型企业把同一张图展开成「SSO、组织联邦、Runner 信任分区、OIDC、制品晋升、灾备、合规证据」。  
**不要给两套产品：规模两档、入口两种。**

---

## 2. 范围与非目标

### 2.1 范围内

- 内部研发全生命周期：克隆 → 评审 → CI → 制品 → 部署到非生产 / 受控生产。
- 身份、仓库治理、密钥、供应链、审计、备份。
- 覆盖 Web、服务端、移动、IaC、容器。

### 2.2 明确不做

| 不做 | 原因 |
|---|---|
| 把 Forgejo 当完整 IDP / 云管 / 日志平台 | 它是 forge，不是 Backstage + 云控制面 |
| 匿名可读、开放注册、公开仓库、未登录能 clone | N/P 都不允许。对外开源是另一套威胁模型 |
| 宣称多活 HA 已生产就绪 | 官方 Helm：*Forgejo is not HA-ready yet*，无 leader-follower，多副本会竞态 |
| 自研 SAST / 密钥扫描 / 依赖机器人 | 用现成工具卡在 CI |
| 用 `host` Runner + 长期 token 跑不可信工作流 | 等于把机器交给任意 workflow 作者 |
| 生产长期云密钥存在 Actions Secrets | 用 OIDC 换临时凭证（16 已支持；`sub` 格式见 §9.2） |

### 2.3 默认假设（与贵司不符时先改这里）

1. **入口二选一或混合**，见 §6.0：N（内网/VPN/ZTNA）或 P（公网 HTTPS 须登录）。默认两边都按「关闭注册 + 必须登录」设计。
2. 人从公司 IdP 来（OIDC 或 LDAP），禁止本地口令当主认证。N 档 2FA 仍建议；P 档 2FA 红线。
3. 生产 Kubernetes / 云账号已存在；本方案管「怎么把代码安全送进去」，不管怎么建 VPC。
4. 语言栈以容器化服务为主，允许少量虚拟机 Ansible；有 Web 面的服务才跑 ZAP。
5. 合规目标按 ISO 27001 / SOC2 证据链设计；具体控制映射可后补，不阻塞落地。

---

## 3. 能力账本（先认账，再设计）

### 3.1 Forgejo 原生有、应作为主干

| 能力 | 用途 |
|---|---|
| Git / PR / Issue / Projects | 协作与变更载体 |
| 组织、团队、仓库权限 | 业务边界 |
| 分支保护、必需评审、必需状态检查 | 变更门禁 |
| Forgejo Actions + Runner | CI/CD 执行 |
| 仓库 / 组织 / 用户 / 全局 四级 Runner 注册 | 信任分区的钩子 |
| 临时 Runner | `one-job` 注册循环，领一单即注销；**不是** daemon 开关（§8.3） |
| Actions OIDC ID Token | 无长期云密钥；16 起新启用 Actions 的仓 `sub` 带数字 ID |
| Authorized Integrations | JWT 访问本实例 API/包/Git，替代长期 token；官方当作 `permissions:` 的替代 |
| 仓库级收窄的 Access Token | 人机凭证最小范围（bot 无 JWT 时的退路） |
| 全局强制 2FA | 人侧第二因素 |
| Package Registry（OCI/Helm/npm/Maven/PyPI/Go/Cargo/Debian/…） | 内部制品 |
| LDAP / OAuth2 / OIDC 登录 | 接公司 IdP |
| Webhook、镜像仓库、迁移 API | 集成与逃生 |
| `DISABLE_REGISTRATION` / `REQUIRE_SIGNIN_VIEW` | N/P 共用：未登录不可见、不能自助开号 |

### 3.2 原生没有、必须外接（否则方案是空的）

| 缺口 | 外接 | 卡在哪 |
|---|---|---|
| 密钥扫描 | **Gitleaks** | PR / 合入 `main` 必过；L 档可加 pre-receive |
| SAST | **Semgrep** | PR 必跑；error 默认建议，毕业后可阻断（§10.1） |
| SCA / 镜像 / IaC / 文件系统 CVE | **Trivy** | PR 扫依赖与 IaC；构建后扫镜像 |
| 依赖更新机器人 | **Renovate** | Bot 开 PR，走同一门禁，不绕过 |
| DAST（对已部署的 HTTP 面） | **OWASP ZAP** | 预发/预览环境，不在冷仓库上跑 |
| SBOM | syft | 构建产物，L 档归档 |
| 镜像签名与准入 | Cosign + Kyverno / Gatekeeper | 发布与集群准入 |
| 运行时威胁 | Falco / 云厂商 GuardDuty（L 档） | 集群侧 |
| 密钥托管 | 公司 Vault / 云 SM；ESO 进集群 | 运行时 |
| 完整审计 SIEM | Forgejo 日志 + Actions 日志 | 运维侧 |
| 真正的多活 HA | 见 §12 | 不假装 |

工具链一句话：**Forgejo 调度；Gitleaks / Semgrep / Trivy 看代码；Renovate 提依赖 PR；ZAP 打活着的环境。** 名词与开源/商业对照见 **附录 A**。

Actions 语法接近 GitHub Actions，**不是 100% 兼容**。黄金工作流只使用已验证子集：`push` / `pull_request` / `workflow_dispatch` / `schedule` / reusable workflow；第三方 Action **按 commit SHA 钉死**，默认源 `DEFAULT_ACTIONS_URL = https://data.forgejo.org`，生产再镜像到本实例。

---

## 4. 参考架构

同一张图。规模（S/L）决定后面有多厚；**入口（N/P）只换最上面那一截**，Forgejo 往后不变。

```
   人 / IDE
        │
        ├──── N 入口：公司网 / VPN / ZTNA ──► 只有进网关才能到 443
        │
        └──── P 入口：公网 HTTPS + WAF ─────► 任何人能摸到登录页
                                              未登录看不到仓库
                        │ SSO / 2FA（P 强制；N 建议，L+N 强制）
                        ▼
        ┌─────────────────────────────────────────┐
        │  Forgejo（源码 · PR · Actions 调度 · 包） │
        │  PostgreSQL · Valkey/Redis · 对象存储     │
        │  DB / Runner / 管理口：永不对公网         │
        └─────┬───────────────┬─────────────┬─────┘
                          │               │             │
              ┌───────────▼───┐   ┌───────▼────┐  ┌─────▼──────────┐
              │ Runner 池 A    │   │ Runner 池 B │  │ Runner 池 C    │
              │ 可信 / 内部    │   │ 隔离 / PR   │  │ 发布 / 生产OIDC│
              │ docker 标签    │   │ 无 secrets  │  │ ephemeral+OIDC │
              └───────┬────────┘   └──────┬─────┘  └──────┬─────────┘
                      │                   │               │
                      ▼                   ▼               ▼
                 扫描+构建+测          只跑 PR 检查      推制品 / GitOps
                      │                                   │
                      └────────────► 包仓库 / OCI ────────┤
                                                          ▼
                                              GitOps 集群（无 Forgejo 长密钥）
```

### 4.1 六个硬边界

1. **Forgejo 进程不执行用户工作流。** 调度在服务端，执行只在 Runner。
2. **Runner 按信任分区，禁止一个全局 docker 跑所有仓库。**
3. **Fork/外部贡献者工作流默认无 secrets**；`pull_request_target` 默认禁用。
4. **生产云权限只用 OIDC 短凭证**，不把 AK/SK 放进 Actions Secrets。
5. **制品晋升靠不可变引用**（digest / 签名），不靠 `latest`。
6. **审计三件套**：Git 历史 + Forgejo 操作日志 + 运行时云审计。缺一就不能回答「谁改了、谁批了、谁发出去的」。
7. **未认证用户拿不到源码。** 无论 N 还是 P。N 靠网络门 + 登录；P 靠登录 + 应用层开关。

### 4.2 入口怎么选

| | **N 内网 / 零信任** | **P 公网须登录** |
|---|---|---|
| 谁适合 | 办公室为主；已有 VPN/ZTNA；监管要求系统不可从公网探测 | 远程/外包多；不想给每人发 VPN；IdP 已支持条件访问 |
| 第一道门 | 进不了网关就没有登录页 | 全世界能打开登录页 |
| 主要威胁 | 内鬼、横向、误配成「网内匿名可看」 | 撞库、扫描、0-day 打登录面 |
| 仍必须登录 | 是。VPN 不是身份 | 是。公网不是公开 |
| S 档最低 | 公司网或一条 VPN；SSO；关注册 | 公网 443 + SSO + 2FA + `REQUIRE_SIGNIN_VIEW` + WAF/限流 |
| L 档最低 | ZTNA（设备/身份入网）+ SSO + 2FA；管理面不出业务网 | 同上 + 条件访问/硬件密钥 + SIEM 打登录 + 源站不暴露 |

**混合合法**：Web/HTTPS 走 P 或 ZTNA，Git SSH 只走 N；或员工走 N、外包走 P 但账号短过期。选混合时在 runbook 写清「哪条 URL 走哪扇门」，不要两套 `ROOT_URL` 配乱证书。

### 4.3 事故按发生概率排（不是按海报吓人程度）

容器逃逸不是内部 Forgejo 上最常见的洞。按**已经发生或几乎每个团队都会踩**的顺序：

| 序 | 事故 | 为什么常见 | 方案里的修法 |
|---|---|---|---|
| 1 | **CI 凭证作用域过宽** | 组织 Secrets 里放了能写很多仓的 PAT；或自动 token 对本仓有写、保护分支没挡住。一个 job 推到不该碰的仓 / 合并 PR / 改 tag | Runner **按组织注册、禁止全局**（执行面隔离）+ **禁止组织级万能 PAT** + 自动 token 当「对本仓有写」来硬化（§9.1） |
| 2 | **密钥进 Actions 日志** | 扫描器把匹配明文打出来。Forgejo 只能打码 `secrets.*` 里登记过的值，**代码里扫出来的密钥不在名单里**。有仓库权限的人都能看日志 | 扫描器强制 redact；禁止把带密钥的 SARIF 贴到 PR；日志保留 **14 天**（§9.4） |
| 3 | **依赖 / Action 投毒** | `uses: foo@v1` 标签被移动；npm/pypi 包被劫持 | SHA 钉死 Action；lockfile；Trivy；Renovate；**ephemeral Runner** 限制失陷后横跳；Cosign 管你**发出去的**制品 |
| 4 | **容器逃逸** | 需要 `privileged`（或挂 Docker socket）再加内核/运行时 0day。默认配置下概率最低 | `privileged: false`、不挂 docker.sock 给不可信 job。**不要把预算优先砸在这里** |

「按组织注册 Runner」修的是 **哪台机器会跑哪个仓的作业**（全局 Runner 上，低信任仓的 job 和下一个发布作业挤在一起）。  
「token 作用域」修的是 **这个作业拿着证件能调哪些 API**。两件都要做，不是同一件事。

官方行为（须按这个设计，不要按 GitHub 2023 年后的默认去猜）：

- 每个 workflow 一张临时 `FORGEJO_TOKEN`，结束即销毁。
- **访问其他仓库返回 404**（不能拿自动 token 去推别人的仓）。
- **对本仓库默认有写权限**（可 push、可走合并/打标签类 API）。`pull_request` 来自 fork 时降为只读。
- 因此「推到不该碰的仓」在 Forgejo 上，主因几乎总是 **自己塞进 Secrets 的宽 PAT / 机器人账号加了太多 team**，不是自动 token 跨仓。自动 token 的真实风险是：**对本仓写过头**（推 `main`、合并自己的 PR）。

---

## 5. 两档强度（S / L）

| 维度 | S 中小企业 | L 大型企业 |
|---|---|---|
| 规模直觉 | 20–200 人，1–3 产品线 | 500+ 人，多事业部、监管或客户审计 |
| 部署形态 | Docker Compose 或单集群 Helm，`replicaCount: 1` | K8s Helm；**仍 `replicaCount: 1`** + 外部 HA 数据面 + 热备实例 |
| 数据库 | 外部 PostgreSQL 单主 + 日备 | CloudNative-PG / RDS 多 AZ；PITR |
| 缓存队列 | 单 Valkey/Redis | Valkey 哨兵或集群 |
| Git/附件存储 | 本地 SSD + 日备 | 对象存储（S3/MinIO）+ RWX 仅必要时 |
| 身份 | OIDC 到公司 IdP；强制 2FA | OIDC + SCIM 或夜间同步；管理员独立 IdP 组；硬件密钥可选 |
| 组织模型 | 少量 org（`platform` / `products`） | 事业部 org + `platform` + `security` + `third-party` |
| Runner | 2 池、**标签分开**；发布标签禁止被业务仓 `runs-on` | 3 池；发布池独立标签 + 仓库级或独立 org 注册；ephemeral |
| 扫描门禁 | 合入：Gitleaks + Trivy 高危 + 单测；Semgrep 建议（**毕业后可改必过，不必升 L**，见 §10.1）；ZAP 打预发（周或每次 main） | 合入再加 Semgrep error + IaC + 许可证 + SBOM；ZAP 预发高危阻断晋升生产 |
| PR 审查 | approvals≥1；作者不能自批；writer 被保护规则完整约束 | 敏感代码**优先独立仓** + 两人；拆不动见 §7.3（CODEOWNERS + 拦正式请求） |
| 制品 | Forgejo Container + npm/PyPI/Go | Forgejo 作源；生产镜像同步到 Harbor/云 Registry 再部署 |
| 发布 | Actions 部署非生产；生产手动/GitOps | 仅 GitOps；prod 无 push 凭据 |
| 入口 N | 公司网或 VPN 到 443；仍须 SSO；Runner 只在内网 | ZTNA + 设备校验；CI 独立 VPC；管理面与 Runner 不出办公网 |
| 入口 P | 公网 443 + 必须登录 + 2FA；WAF/限流；Runner 不出公网 | 同上 + 条件访问；源站隐藏；登录进 SIEM |
| 共用 | 关注册、`REQUIRE_SIGNIN_VIEW`、仓库 private、DB/Runner 不对公网 | 同左，审计更长 |
| 审计 | Actions 日志 14 天；Git 仍长期 | 扫描报告进 DefectDojo；登录/权限进 SIEM 1 年+ |
| 人员 | 平台 **≥ 0.3 FTE**（低于则砍到 §15 MVP，不上 Dojo/ZAP/Renovate/OIDC；只能宣称 MVP） | 平台组 + 安全冠军 + 变更咨询会 |
| 目标 RTO/RPO | RPO ≤ 24h，RTO ≤ 4h | RPO ≤ 1h，RTO ≤ 1h（演练过） |

**升级原则（两件不同的事，不要绑在一起）**：

- **升 L**：产品线超过 5 条、或出现监管审计、或 Runner 开始碰到别人的密钥。改的是组织形态（三池、GitOps、Dojo、Cosign）。入口从 N 改 P（或反过来）只改边缘，不换 Forgejo。升档改强度，不换软件。
- **单道闸从建议升到阻断**：与升 L **脱钩**。S 可以把 Semgrep error（及表里其它「S=建议」的合入相关闸）改成必过，不必变成 L。判据见 §10.1，不是「人多了就阻断」。

---

## 6. 暴露面、身份、组织、仓库

### 6.0 两种入口（N 与 P），都禁止匿名

规模是 S/L；入口是 N/P。四格都能装同一套 Forgejo。

**共用底线（N 和 P 都做）**

| 控制 | 作用 |
|---|---|
| `DISABLE_REGISTRATION = true` | 不能自助开号 |
| `REQUIRE_SIGNIN_VIEW = true` | 未登录看不到仓库、代码、Issue、包、Actions |
| 仓库默认 private | 没有「链接分享即可见」 |
| SSO（OIDC/LDAP），禁止本地口令当主认证 | 身份在 IdP |
| 匿名不能 `git clone` | HTTPS 要 token，SSH 要已登记密钥 |
| PostgreSQL / Valkey / Runner / metrics **不对公网监听** | 控制面再怎么暴露，执行面和数据面不暴露 |
| 外包若有：独立团队、短过期、无 Runner 管理权 | 人的边界 |

`REQUIRE_SIGNIN_VIEW` 在 **N 也要开**。内网不等于可信：扫到地址就能读源码，是最常见的「我们以为在内网所以没关系」。

---

#### N · 内网或零信任

人先进入一张被公司控制的网，再登录 Forgejo。

| 层次 | S | L |
|---|---|---|
| 网络门 | 办公网 ACL，或一条 WireGuard/IPSec VPN | ZTNA：身份 + 设备才发到 443（IAP、Cloudflare Access、Tailscale Funnel 关闭公网、专线） |
| DNS | 内网解析 `git.corp.example` | 分内外；公网无 A 记录，或只指到 ZTNA |
| TLS | 内网 CA 或公网证书都可以 | 正规证书，避免开发机关校验 |
| 2FA | 建议 | 强制（内网被跳板后仍要第二因素） |
| Git SSH | 内网 22/2222 | 只走堡垒或 ZTNA，不直出 |
| WAF | 可省略 | 仍建议挡管理接口误暴露 |
| 威胁重心 | 横向移动、Runner 扫办公网、离职账号 | 同左 + 供应商 VPN 账号 |

N 档常见翻车：VPN 进了以后匿名可看；或 Forgejo 和 Runner 跟办公桌面同一二层，workflow 扫打印机。Runner 必须在 **CI VLAN/VPC**，即使整个系统都在内网。

---

#### P · 公网须登录（非匿名）

443 在公网上，登录页可以打开，**登录前没有业务数据**。

| 层次 | S | L |
|---|---|---|
| 网络门 | 无（全世界能 SYN） | 可选：IdP 条件访问、地理/设备；**不能替代登录** |
| TLS | 公网证书、HSTS、正确 `ROOT_URL` | 同上 + 隐藏源站 IP |
| 2FA | **强制** | 强制；管理员硬件密钥 |
| 登录面 | 反代限流、失败锁定 | WAF + 限流 + 登录进 SIEM |
| 搜索引擎 | `robots.txt` Disallow | 同上，定期搜实例域名是否被收录 |
| Git SSH | 建议只开 HTTPS+token，少开公网 SSH | SSH 若要开：非 22、密钥-only、独立入口 |
| Runner | 只出站连 Forgejo，无公网入站 | 独立出口 VPC，无回连办公网 |
| 威胁重心 | 撞库、漏洞打登录、Action 供应链 | 同左 + 针对性钓鱼 |

P 档红线：2FA、关注册、`REQUIRE_SIGNIN_VIEW`、Runner 不出公网。少一项就按「公开了」处理。

---

#### 对照（避免混用时漏项）

| 项 | N | P |
|---|---|---|
| 未进公司网能否看到登录页 | 否 | 是 |
| 未登录能否看到仓库 | 否 | 否 |
| 2FA | S 建议 / L 强制 | S/L 都强制 |
| WAF / 登录限流 | L 建议 | S 就要有 |
| 公网 DNS | 无或仅 ZTNA | 有 |
| Runner 入站 | 仅内网管理 | 无 |
| 把「在网里」当授权 | **禁止** | 不适用 |

从 N 迁 P：先开 2FA 和限流，再放公网 DNS，最后才拆 VPN。从 P 迁 N：先加 ZTNA，再收 DNS，登录策略不要放松。

### 6.1 实例级铁律（S/L 共用）

```ini
[service]
DISABLE_REGISTRATION = true
REQUIRE_SIGNIN_VIEW = true
ENABLE_NOTIFY_MAIL = true

[admin]
DISABLE_REGULAR_ORG_CREATION = true

[repository]
MAX_CREATION_LIMIT = 0
ALLOW_FORK_WITHOUT_MAXIMUM_LIMIT = false

[actions]
LOG_RETENTION_DAYS = 14
ARTIFACT_RETENTION_DAYS = 14
```

- 人：IdP 登录。P 档全员 2FA；N 档 L 强制、S 建议，管理员两边都强制。在 `Identity & access` 核覆盖率。
- 容器+反代认证（`[service] ENABLE_REVERSE_PROXY_AUTHENTICATION`）：`[security] REVERSE_PROXY_TRUSTED_PROXIES` 写成反代网段，**不要** `*`。键不在 `[service]`。环境变量 `FORGEJO__security__REVERSE_PROXY_TRUSTED_PROXIES`。16 容器镜像不再默认 `*`。
- 仓库：默认禁止用户自建；由 **org 模板 + 平台机器人** 开库，避免恶意空库挂 `on: push` 工作流打 Runner。
- 组织：禁止普通用户建 org（否则 `MAX_CREATION_LIMIT` 被绕过）。S 档可把 `MAX_CREATION_LIMIT` 放宽到小整数，但必须同时禁止自建 org。

L 档追加：

- 关闭或严格限制「公开仓库」。
- 管理员账号与日常研发账号分离；应急 break-glass 账号离线保管。
- 定期（季度）导出成员/团队/仓库权限，对账 IdP 离职。

### 6.2 组织拓扑

```
company-platform     平台模板、可复用 workflow、策略
company-security     安全规则、Semgrep pack、例外申请
<bu>-apps            各业务应用
<bu>-libs            共享库
third-party          供应商交付物（默认更狠的门禁、独立 Runner）
```

团队权限只分下列档，**Owner/管理员人数是真正的控制点**（见 §7.3）：

| 团队 | 权限 | 谁 |
|---|---|---|
| `maintainers` | 写代码、合并（仍过保护分支） | 模块负责人；**尽量不是**仓库 Owner |
| `developers` | 写分支、开 PR，不能推保护分支 | 开发 |
| `ci-bots` | 见 §9.1.2：Renovate 与发布 **两套身份** | 不能是仓库 Owner/管理员 |
| `security-reviewers` | 写或审批白名单，作第二人 | 钱路/IAM/密钥仓的第二审批人 |
| `auditors` | **只读** | 合规、外部审计 |

每个仓 **Owner/管理员 ≤ 2**（平台应急 + 业务负责人），日常开发用 writer，不用 owner 合 PR。

禁止个人用户仓库作为生产代码源。所有要上线的代码必须在 org 下。

### 6.3 仓库模板（开库即带门禁）

平台维护 `template-service`：

- `.forgejo/workflows/ci.yml`（status check 怎么写见 §7.3，不要猜 `ci` 这个名字）
- 默认 `LICENSE` / `SECURITY.md` / `CONTRIBUTING.md`（含「纯 LGTM 不算审完」）
- `.gitleaks.toml`、`.semgrep.yml`、`renovate.json`
- 分支保护、CODEOWNERS、钱路拆仓或路径门禁：**一律见 §7.3**。模板不默认塞 CODEOWNERS。

---

## 7. 变更控制

### 7.1 主干策略

- 默认 **trunk-based**：短命分支 → PR → `main`。
- 发版用 tag：`vX.Y.Z`，由 CI 打不可变制品。
- `main` 与 `release/*` 为保护分支。
- **保护标签**（Settings → Tags）：模式至少 `v*`。白名单 = `release-bot`（及必要时 Owner）。**空名单 = 谁都不能打**。Writer 打 tag → **422** `user not allowed to create protected tag`。否则任何人都能触发 §11。验收见 §17。

### 7.2 PR 与威胁模型（必须写进规范）

官方安全模型要点（落地成制度，不是建议）：

| 场景 | 风险 | 规定 |
|---|---|---|
| 对保护分支有直接写权限 | 可建未保护分支挂 `on: push` 跑任意 workflow | 写权限只给 maintainer；其他人只走 PR |
| 第一次来自 fork 的 PR | 需仓库协作者批准才跑 Actions | 内部默认 **禁止 fork 工作流**；协作只在同 org |
| 后续 fork PR | 自动跑，且可新增 workflow | 因此内部关掉 fork CI |
| `pull_request` | 无 secrets，相对安全 | PR 检查只放这一类 |
| `pull_request_target` | 用目标分支代码 + **有 secrets** | **默认禁用**；例外需安全评审 |
| 远程 Action `uses: org/action@v1` | 标签可被移动 | **必须 `@<commit-sha>`**；L 档只允许本实例镜像 |

### 7.3 PR 审查（以本实例实测为准，2026-08，**Forgejo 16**）

下列行为已在 **Forgejo 16** 上测过，**覆盖此前文档里的猜测**。升 17 要重测。

#### 作者不能批自己（已证实）

`POST` 批准自己的 PR → **422** `approve your own pull is not allowed`。这条成立，写入验收。

`required_approvals = 0` 时，有写权限的作者仍可走普通 merge。故仍须 **`required_approvals ≥ 1`**。

#### 分支保护完整约束 writer，对 owner/管理员是建议性的

普通 merge `{"Do":"merge"}` 和 **`force_merge: true`** 不是同一条路径。只测前者会误判。

本实例实测：

| 身份 | `apply_to_admins` | `force_merge=true` |
|---|---|---|
| write 协作者（非管理员） | — | **405 拦住** |
| 仓库 owner/管理员 | `true` | **200 绕过** |
| 仓库 owner/管理员 | `false` | **200 绕过** |

另：owner/管理员可 **DELETE 保护规则（204）**，规则删了就没有保护。

结论：**控制点不在规则里，在「谁是管理员」。** `apply_to_admins` 挡的是管理员走普通合并按钮/普通 merge API，**挡不住 `force_merge`，也挡不住删规则。**

规定：

- Writer（developers/maintainers 非 owner）：靠 `required_approvals`、禁止直推、status check——对这一层，保护规则是硬的。
- Owner/管理员：人数 **每个仓 ≤ 2**；日常开发账号 **不要** 给 Owner；CI bot **不要** 给 Owner。
- 审计：对 `force_merge=true` 的合并、以及对保护规则的 DELETE/PATCH，打进 SIEM 或至少平台周报。没有这条审计，管理员绕过是静默的。
- Break-glass：两人在场用 **管理员** 做 `force_merge` 或临时删规则，当天开 issue（谁、哪条 PR、API 还是 UI、何时恢复规则）。不要指望靠关掉 `apply_to_admins` 当开关——那个开关管不到 `force_merge`。

#### CODEOWNERS（本实例已复现；平台行为只写在这里）

官方（Forgejo 16：[Review requests and code owners](https://forgejo.org/docs/v16.0/user/collaboration/pull-requests-and-git-flow/#review-requests-and-code-owners)）：Go 正则 + 用户或 `org/team`，开 PR 时自动请求审查。

**此前「四位置未复现」作废。** 那次是环境配错：仓里同时躺多份 `CODEOWNERS`，根目录还用了 GitHub glob。清成 **根目录一份 + Go 正则** 后立刻生效。

**只放仓库根一份。** `.gitea/` / `.forgejo/` / `docs/` 是上游 Gitea 兼容路径，留第二份只会再踩多文件冲突，当坑不当时选项——正是第一次误判「不支持」的成因之一。位置变量已隔离（2026-08-29）：四个标准位置只剩根目录一份（另三处 API 均不存在），重开 PR：

```
requested_reviewers                    → ['renovate']
非 code owner 批准（已满足 approvals=1） → 200
merge                                  → 405 [reason: There are official review requests]
code owner 批准                         → 200
merge                                  → 200
```

根目录单独一份就够，硬门仍成立。不要再讨论「哪个位置优先」。

硬门禁（本实例已测）：

- 只开 CODEOWNERS、不开「拦正式审查请求」→ 仍是通知：`required_approvals` 是人数，别人批了就能合。
- **CODEOWNERS + `block_on_official_review_requests`** → 硬门。非负责人批准即使凑够 `required_approvals=1` 仍 **405** `There are official review requests`；负责人批准才 **200**。
- 请求必须被标成 **official**：点名的人/组要有写权限或在审批白名单。只读 `auditors` 批了也不算。
- 语法是 Go 正则（`src/.*` 或 `^secrets/.*`）。抄 `src/**` 会静默零匹配。
- `CODEOWNERS` 自己、以及 `.gitleaks.toml` / `.semgrep.yml` / `zap.yaml` / `.zap/rules.tsv`，都要有规则——否则同一 PR 里引入漏洞再写进忽略文件没人拦。例外过期日用 CI 解析，格式不对或过期则 job 失败（自觉不算治理）。
- Owner 仍可用 `force_merge` / 删规则绕过（见上）。

钱路 / IAM / 密钥两人审：

| 做法 | 何时 |
|---|---|
| 敏感代码 **独立仓库** + `required_approvals = 2` + 审批白名单 | **首选**。组织边界最干净 |
| **CODEOWNERS + 拦正式请求**（Go 正则、一份文件、负责人有写/白名单） | 大仓暂时拆不动。抽检：非负责人 Approve → 405；负责人 Approve → 200 |
| 整仓 `required_approvals = 2` | 小仓、拆不出去也不想养 CODEOWNERS |
| `protected_file_patterns` | **不是**多人审批——冻结这些文件（直推和合并都拒） |
| 自定义 CI：`git diff` 命中则失败 | 仅过渡脚本 |

组织模板 **不**默认塞 CODEOWNERS。只用在选定的大仓，并做一次上面的 405/200 抽检。

#### 状态检查：名字写错会把分支锁死

本实例：无 CI 的仓套 `status_check_contexts: ["*"]` → **永久不能合**（fail-closed，不是真空通过）。**禁止组织级**给所有仓打 `["*"]`。

有 CI 的仓，context **不是** job 名、也不是 `ci`：

- 实际格式：`<workflow 名> / <job id> (<事件>)`
- workflow 文件没写 `name:` 时，前半段为空，context **以斜杠开头**，例如 `/ no-checkout (push)`（本实例 `ci.yml`）
- 写成 `["ci"]` 这类猜的名字：**job 绿了照样 405**，分支锁死，比 `["*"]` 更糟

规定：

- 有 workflow 的应用仓：用 `["*"]`（本实例上比手填名字稳），或从 `GET /repos/{o}/{r}/commits/{sha}/statuses` 的 `context` **逐字复制**。
- 文档仓、无 workflow 的仓：**不要**开 status check。
- 模板分两种：`template-service`（有 CI + `["*"]`）、`template-docs`（无 status check）。
- **`paths-ignore` 命中的 job 不上报 status。** Forgejo 没有「跳过当 success」。必检 job 加了 `paths-ignore`，只改文档的 PR 会 **405 Not all required status checks successful**，永远合不了。必检 job 不要 `paths-ignore`；文档仓用无 check 模板。

#### 纯 LGTM 等于没审

规范，不是开关。空批准照样计入 `required_approvals`。写入 `CONTRIBUTING.md`，靠抽查，**不要写进平台验收当「Forgejo 会拦」**。

### 7.4 提交签名（L 必做，S 建议）

- 要求 GPG 或 SSH 签名提交。
- 保护分支开启「拒绝未签名」。
- CI 机器人使用独立密钥，公钥进 org。

### 7.5 预接收钩子（L）

在 Forgejo 预接收或服务器 hook：

- 阻止超大二进制（用 Git LFS）。
- 可选：gitleaks 预接收（会拖慢 push，先对 `platform` 和 `security` 启用）。

S 档把密钥扫描放在 CI 即可，但必须是 **合并必过**，不能只警告。

---

## 8. Actions 与 Runner 信任分区

这是本方案的脊梁。配错 Runner，前面所有权限都是摆设。

### 8.1 标签与隔离级别

| 标签 | 执行器 | 谁可以用 | 禁止 |
|---|---|---|---|
| `docker` | 每 job 新容器 | 内部可信仓库 | `privileged`、`network: host` |
| `docker-dind` | 需要 docker build | 仅构建仓库，单独池 | 与密钥扫描池混部 |
| `lxc` | 系统容器 | 需要完整 OS 的构建 | 无资源限额，L 档慎用 |
| `host` | 无隔离 | **默认禁用** | 任何不可信或多人共享仓库 |

默认 Runner 配置（与官方安全文档对齐）：

- `container.privileged: false`
- `container.network: ""`（每 job 独立网络）
- `container.valid_volumes: []`
- 不要把 Runner 的 docker 登录到「比作业权限更高」的私有仓库。
- `container.options` 加 `--memory` `--cpus`；`runner.capacity` 与之匹配。
- `runner.timeout` 不要用默认 3 小时当容量规划。

**DinD**：需要 `docker build` 时用独立池 + 受限 socket，不要 `docker_host` 指向外层特权 daemon 给不可信作业。

### 8.2 注册范围

| 范围 | 用途 |
|---|---|
| 仓库级 | 最高敏仓库（密钥、证书、计费） |
| 组织级 | 默认。`bu-apps` 的 Runner 跑不了 `company-platform` 的作业，反之亦然 |
| 用户级 | 禁止（个人仓库不是生产源） |
| 全局 | **禁止**。全局 Runner = 任意仓库 RCE |

### 8.3 三池模型（L 标准；S 可把 B/C 合成一台但逻辑仍分标签）

**池 A · internal**

- 组织级，仅 `internal` 团队的仓库。
- 跑单测、扫描、构建。
- 可读取组织 Secrets（非生产）。
- 网络：出网白名单（包源、Trivy DB、本实例）。

**池 B · pr-isolated**

- 只处理 `pull_request`。
- **不挂组织 Secrets**。
- 更狠的资源上限；无 Docker socket。
- 即使 PR 改了 workflow，也拿不到生产或云凭证。

**池 C · release**

- 仅 `main` / tag / `workflow_dispatch`（受限人）。
- **独立标签**，例如 `release-oidc`，**不准**出现在业务仓模板的 `runs-on` 里。业务仓 CI 只用 `docker` / `pr-isolated`。
- 注册范围：发布相关仓 **仓库级**，或单独 `company-products` org；禁止挂在整个 `<bu>-apps` 上（否则黑客马拉松仓能调度到发布机）。
- S 档若只有一台机器：仍必须 **两个标签、两份 runner 注册**（同一宿主机也比全局好）。
- 只通过 OIDC 换云凭证 / 集群凭证。
- 与办公网隔离。

上线当天验收：在一个无关仓提交 `runs-on: [release-oidc]`，必须 **排不到** 发布机。排得到就不算隔离。

**ephemeral 不是配置开关。** 本实例：`forgejo-runner daemon` **直接拒绝** ephemeral；`one-job` 领一单后**永久注销自己**。`restart: unless-stopped` 救不回来。真实形态是注册循环：登记 → `one-job` → 销毁/再登记（作业队列拉 VM/Pod）。泄露也只能领一单——前提是走这条循环，不是给长驻 daemon 加个旗标。S **默认不上** ephemeral（划在「<0.3 FTE 只做 MVP」闸的另一侧）。做不到循环就用长驻分标签 Runner。

### 8.4 工作流分层（禁止每个仓库自写一套「能部署生产」的 YAML）

`company-platform` 提供可复用工作流，业务仓库只能 `uses:` 本实例 SHA：

1. `ci.yml`：格式 → 单测 → **Gitleaks** → **Semgrep** → **Trivy** fs/IaC → 构建（不推生产 tag）
2. `build-publish.yml`：仅 `main`/tag；推 OCI；**Trivy image**；syft SBOM；cosign 签
3. `deploy-nonprod.yml`：OIDC 到非生产
4. `dast-zap.yml`：预发就绪后跑 **OWASP ZAP**（起步 baseline；长期 `zap.yaml` + `-autorun`）。**不要写 `on: workflow_run:`**——本实例三种名字 × 两种 types 共 17 次，**一次都没触发**。三选一：① 部署 workflow 最后一个 job（`needs:`，推荐）② 部署脚本调 `workflow_dispatch` ③ `schedule` 兜底。报告挂 artefact，不挡冷 PR
5. 生产：不在业务仓库里写 `kubectl apply`；更新 GitOps 仓或发 release event

业务仓库若复制粘贴一套带 `id-token` 的 deploy，PR 检查失败（可用 Semgrep 自定义规则扫 workflow）。

### 8.5 Action 供应链

- `DEFAULT_ACTIONS_URL` 指向 **本实例镜像**（L）或 `https://data.forgejo.org`（S，可接受）。
- 允许列表：`actions/checkout`、`actions/setup-*`、自建 `company-platform/actions-*`。
- 引用格式：`uses: https://git.example.com/actions/checkout@<full-sha>`。
- 季度升级 SHA，出 PR，人工看 diff。

---

## 9. 密钥与身份联合

### 9.1 分类

| 种类 | 存哪 | 谁碰 |
|---|---|---|
| 人的登录 | IdP | 人 |
| 仓库加密变量（非生产测试口令） | Forgejo Secrets | 池 A 的 job |
| 云 / 集群 / 生产 | 根本不进 Forgejo | OIDC 换发 |
| 镜像签名密钥 | KMS / 硬件 | 池 C |
| Webhook / Bot | 见 §9.1.2，**两套身份** | 禁止一张「All 组织」PAT |

### 9.1.1 自动 token 与「过宽」到底是哪一种

| 凭证 | 能做什么 | 过宽时的事故 | 规定 |
|---|---|---|---|
| `FORGEJO_TOKEN`（自动） | **仅本仓**；默认**写** | 作业给 `main` 推提交、用 API 合并 PR | 保护分支拦 writer；bot 不能是 Owner（Owner 能 `force_merge`） |
| 组织 Secrets 里的 PAT | 看你给这个人/token 开了哪些仓 | **跨仓 push** | **禁止 All-org 写**。Renovate 用 §9.1.2 模型，不是「一人一仓」 |
| Authorized Integration JWT | 你勾的 Capabilities | audience/仓库选 `*` | 必须绑死 Source Repository + workflow 文件名 |
| Runner 注册范围 | 不发 API，决定谁的代码在这台机器上跑 | 全局或大 org 发布标签被乱选 | 禁止全局；发布用独立标签（§8.3） |

GitHub 风格 `permissions:` 在 **Forgejo 16.0.3 已证伪，不是控制**。官方把 [Authorized Integrations](https://forgejo.org/docs/v16.0/user/api/authorized-integrations/) 写成自动 token 提权的替代，而不是在 workflow 里用 `permissions:` 给自己加权限。

本实例（同一 workflow 两个 job，唯一差异是 job 级 `permissions`，都用自动 token 推**非保护**分支）：

| job | YAML | 结果（2026-08-29） |
|---|---|---|
| `perm-restricted` | `contents: read` | 分支建出：`b79dbd47ab` `probe restricted` by ci |
| `perm-control` | `contents: write` | 分支建出：`a5ffef2a17` `probe control` by ci |

两个 job 的 Actions 状态都是 success，那只是 shell 退出码。决定性证据是两条分支都在。`contents: read` **不会收回**自动 token 的写权限——键被解析、被忽略。对照组证明 push 通路本身没问题。收回写权限的是**保护分支**（以及 bot 不当 Owner），不是 YAML。YAML 可留着当意图注释，**不要对研发说「写了 permissions 就安全」**。

```yaml
# 意图文档。本实例 16.0.3：contents: read 仍能 push 非保护分支。
permissions:
  contents: read
  pull-requests: read
  packages: read
```

升 17 或换实例：用同一对照再测一次，结果写入 runbook。`actions/checkout` 在不可信上下文设 `persist-credentials: false`。

### 9.1.2 Renovate / 发布机器人：两套身份，禁止套「一人一仓」

Renovate 的产品形态是 **一个身份给很多仓开 PR**。仓库级 token 按仓发养不起，硬套会导致：要么 Renovate 瘫痪，要么又发一张组织万能 PAT。

| 身份 | 允许 | 禁止 |
|---|---|---|
| `renovate-bot` 用户 | 向非保护分支推修复分支、**开 PR** | push 保护分支、merge、write:package、管理 Runner、仓库 Owner |
| `release-bot` 用户 | 仅制品 org / 发布仓：写包、打 tag（若保护 tag 则走白名单） | 给业务仓开 PR、写源码 |

`renovate-bot` 必须是 **writer 不是 Owner**。对 writer，保护规则是硬的。它若被加成管理员，即可 `force_merge`。Renovate 的 PR 走与人相同的门禁：CI + 他人批准。

组织 Secrets 里只放这两张身份的凭证，scope 按上表每年复核。发现 `renovate-bot` 能 merge 或能推 `main` → 立刻作废。

### 9.2 OIDC（16.0，S 能做就做，L 强制）

文档（Forgejo 16）：[Security OpenID Connect](https://forgejo.org/docs/v16.0/user/actions/security-openid-connect/)。

工作流：

```yaml
enable-openid-connect: true
```

（`permissions: id-token: write` 仍可当意图注释；提权走 §9.3，不靠 YAML。）

云侧信任条件至少校验：

- `iss` = `https://git.company.example/api/actions`（16 文档格式，带 `/api/actions`）
- `aud` = 明确 audience
- `sub` **精确到这一仓这一 ref**，不要 `repo:*`

**16 的 `sub` 有两种形态**（按「何时启用过 Actions」分，不是按实例版本一刀切）：

| 仓何时启用 Actions | `sub` 里的 `[repository]` | 例子 |
|---|---|---|
| **16 之前**就开过 | `owner/name` | `repo:org/svc:ref:refs/heads/main` |
| **16 之后**才开，或关过再开 | `owner-<id>/name-<id>` | `repo:org-12/svc-34:ref:refs/heads/main` |

关再开会 **永久** 切到带 ID 的格式，不能退回。云 trust 必须按仓核对实际 `sub`（解码一枚 token），不要抄一份 glob 套全公司。`pull_request` 事件的 `sub` 是 `repo:[repository]:pull_request`，没有 ref。

测法在 **云 IdP**，不在 Forgejo UI：workflow 打出 token，记下 `iss` / `sub` / `aud`，与该仓的 trust 逐条比对。失败标准：全公司一份 `repo:*` glob。

配错 trust 等于给任意 workflow 开云。这是 L 档变更咨询会的固定检查项。

### 9.3 Authorized Integrations（16.0 正式能力）

文档（Forgejo 16）：[Authorized Integrations](https://forgejo.org/docs/v16.0/user/api/authorized-integrations/)。用途：Actions 需要写包、打 tag、跨仓 API，但自动 `FORGEJO_TOKEN` 不够。官方明确：这是给 workflow **提权** 的路，替代在 YAML 里扩 `permissions:`。

- 本实例优先 **Forgejo Actions (Local)**。v16 官方四项：[Authorized Integrations](https://forgejo.org/docs/v16.0/user/api/authorized-integrations/)
  - **Source Repository**：必选（官方；转仓后要重选）。
  - **Workflow file**（无目录，可通配）：**空 = 该仓任意 workflow**。
  - **Git reference**（可通配）：**空 = 任意 ref**。
  - **Event**：**空 = 任意事件**。
- 本方案比官方严：四项都填，禁止靠「空=任意」宣称绑死。audience 不是机密，可进仓；JWT 用 `::add-mask::`。
- 测法（L 验收）：打开每条 Local Integration，记下 Source Repo / workflow / ref / event / capabilities；用**另一仓或另一 workflow 文件**要 JWT 调写包 API，必须失败。Event/workflow/ref 为空仍勾「已绑死」= 失败。
- 跨 Forgejo 或云签发才用 Generic JWT，`iss` 必须 https + OIDC discovery。
- 非 Actions 的 bot（Renovate）仍用收窄 PAT；有 JWT 路径的发布作业不要再发长期写 token。

### 9.4 日志与泄漏（已发生过：扫描器把密钥打进日志）

Forgejo Runner **只会尝试打码登记在 `secrets` 里的值**。Gitleaks/Semgrep 从**代码**里扫出来的串不在名单中，会原样进日志。有该仓库读权限的人都能打开 Actions 日志。这是第二常见事故，不是理论。

规定：

| 控制 | 做法 |
|---|---|
| 日志保留 | `[actions] LOG_RETENTION_DAYS = 14`（官方默认 **365**） |
| 工件保留 | `[actions] ARTIFACT_RETENTION_DAYS = 14`（[v16.0 cheat sheet](https://forgejo.org/docs/v16.0/admin/config-cheat-sheet/#actions-actions) / [Actions 管理](https://forgejo.org/docs/v16.0/admin/actions/) 默认 **90**）。扫描 SARIF/JSON 权限随仓读，未 redact 的工件比日志活得更久 |
| Gitleaks | 必须 `--redact`；报告里只留指纹/规则 ID，不留完整 secret |
| Semgrep | 禁止把匹配原文贴到 PR 评论。CI 用 JSON 工件；规则侧对密钥类规则做 redact / 只报 `checksum`。密钥类发现以 Gitleaks 为准，Semgrep 不要重复打印同一串 |
| 工件内容 | SARIF/JSON 可进 artefact，**不要** `echo` 进 step log。下工件 `grep` AKIA / `ghp_` / `BEGIN` 必须空。只查 step log 不算过 §9.4 |
| 谁能看 | 默认随仓库读权限。密钥类仓库把 Actions 单元收到 maintainer |
| 发现泄漏 | 当作密钥已暴露：轮换、作废 token、日志**和工件**保留期内假定内部可读 |

打码不是加密。14 天窗口内，能看这个仓的人等于能看扫出来的明文。所以 **redact 比缩短保留更重要**；日志和工件两条都做。

---

## 10. 供应链与制品

### 10.1 门禁矩阵（合并到 `main` 的必过）

| 门 | S | L | 失败策略 |
|---|---|---|---|
| gitleaks | 必过 | 必过 | 阻断 |
| 单测 / 构建 | 必过 | 必过 | 阻断 |
| Semgrep error | 建议（默认不进必过；毕业后可必过） | 必过 | 未毕业：黄灯能合；毕业后 / L：阻断 |
| Trivy HIGH/CRIT 依赖 | 必过（可有限例外） | 必过 + 例外工单 | 阻断 |
| Trivy IaC | 建议（默认不进必过；毕业后可必过） | 必过 | 未毕业：黄灯能合；毕业后 / L：阻断 |
| 许可证 | 可选 | 必过（拒绝 GPL 进专有产品等） | 阻断 |
| Dockerfile base 白名单 | 建议 | 必过 | 阻断 |
| SBOM 上传 | 建议 | 必过 | 阻断 |
| Cosign 签名 | 可选（单仓库+只信本 CI 时可缓） | **生产镜像必签、集群必验** | 无签名不可进生产 |
| **ZAP DAST** | 预发：每次 `main` 或每周；High 告警（起步 baseline / 等价 AF 被动计划） | 每次晋预发必跑 AF 计划；High/Crit 阻断晋生产 | 不挡冷 PR（没有活 URL）；`activeScan` 不进组织模板 |

例外：S 档在 PR 评论写明过期日。L 档在 `company-security` 开「风险接受」issue，过期自动变红。

**S 合入硬门**只有 Gitleaks + 单测/构建 + Trivy 高危。这三样不是一类东西：Gitleaks 二元、调完配置后误报极低；Trivy 高危是 lockfile 里有没有这条 CVE（「不可达」走例外，不是检测歧义）；**Semgrep error 的误报完全取决于规则集**，陌生团队拿 `p/default` 开箱阻断，过几周那道闸就会被关。所以 Semgrep 在 S **必须跑、必须接入、默认不进保护分支必过**——一条仅 Semgrep error、其余绿的 PR **能合**。§17 写「Semgrep 已接入」不是把 S 的黄灯改成阻断。

**毕业（建议 → 阻断），与升 L 脱钩。** 适用于上表 S 列为「建议」的合入相关闸，Semgrep error 是主例；Trivy IaC / Dockerfile 白名单同理。三条同时成立才改必过：

1. 规则集已裁：能指出留下和拿掉哪些 pack，不是 `p/default` 开箱。
2. 会红的规则有 owner（谁看、多久响应、修不了怎么豁免）。答不上不要切阻断。
3. 拿得出周报：**新增** error 连续若干周误报为零（基线里的 ignore 不算）。周数不写死，能出示那份周报就算。

达标后把该闸设成必过 status check，**仍是 S**。未达标就阻断 → 闸被关掉；永远建议又没 owner → 评论没人理。两种都是失败。L 默认 Semgrep error 必过（L 有人值班），不是「S 永远不能阻断」。

### 10.1.1 扫描栈怎么串（含 ZAP）

| 工具 | 看什么 | 何时 | 输入 |
|---|---|---|---|
| Gitleaks | 密钥、token、私钥 | PR 与 `main` | Git 历史 / diff |
| Semgrep | 代码缺陷、注入、不安全 API、危险 workflow | PR 与 `main` | 源码 |
| Trivy | 依赖 CVE、镜像 CVE、IaC 误配、密钥残留 | PR（fs/config）+ 构建后（image） | lockfile / Dockerfile / 镜像 |
| Renovate | 过期依赖 | 定时 Bot PR | 清单文件 |
| **ZAP** | 运行中 HTTP 的 XSS、CSRF、头缺失、鉴权绕过等 | **环境起来之后** | 预发 URL + 测试账号；计划在 `zap.yaml` |

ZAP 不是第四个「扫仓库的工具」。没有可访问的预发/预览，ZAP 没有意义。

#### 官方自动化：Automation Framework（长期主路径）

官方说法（[Automation Framework](https://www.zaproxy.org/docs/automate/automation-framework/)）：**AF 会逐步取代「命令行参数 + Packaged Scan」那种写法。** 一份 YAML **plan** 描述目标、登录、爬什么、被动还是主动、出什么报告、怎样算失败；不绑任何容器。Forgejo 上的长期形态就是这份 plan + `-autorun`，不是把 `zap-baseline.py` 的旗标越堆越长。

Plan 结构：

- **`env.contexts`**：一个或多个站点（`urls` / `includePaths` / `excludePaths`）；认证写在 context 里，方法包括 `manual` / `http` / `form` / `json` / `script` / `autodetect` / `browser` / `client`。口令用 `${ZAP_USER}` 这类变量，**不要写进 YAML**（系统环境变量同名时优先于 plan 里的 `vars`）。
- **`jobs`（按出现顺序执行）**：本方案会用到的核心 job —— `spider` / `spiderAjax` / `spiderClient`（爬）、`passiveScan-config` + `passiveScan-wait`（被动）、`activeScan`（主动，只打有授权的预发）、`openapi` / `graphql` / `soap`（有契约再加）、`alertFilter`（已知误报）、`report`、`exitStatus`（失败门槛）。顺序有意义：先爬再 `passiveScan-wait`；`alertFilter` 必须在出告警之前。
- **失败怎么算**：`exitStatus` 的 `errorLevel` / `warnLevel`（Informational / Low / Medium / High）。默认 `-cmd -autorun` 退出码：0 成功、1 有 error、2 仅 warning。门禁看退出码，不要再解析 HTML。
- **生成与校验**：`zap.sh -autogenmin` / `-autogenmax` / `-autogenconf` 出模板；`-autocheck zap.yaml` 先校验再进 CI。`addOns` job **已废弃**（官方写 depreciated、不再做事）；要装插件用命令行 `-addoninstall` / `-addonupdate`，不要写回 plan。

打包扫描 **没有删**：`zap-baseline.py` 等仍在 Docker 镜像里，且官方正在把它们迁到 AF 底下（`--auto` 即将成为默认；`--plan-only` 可只吐 YAML 不跑）。**Packaged Scan 只跑在 Docker 里；要登录、多站点、自定义策略时，官方明确 AF 更合适。** GitHub 上的 `zaproxy/action-baseline` / `zaproxy/action-af` 是同一套能力的 Marketplace 包装，Forgejo **不要**当原生 Action 依赖，执行面用镜像 + `zap.sh`。

#### Forgejo 怎么收：先 baseline，规则复杂再 `zap.yaml`

| 阶段 | 用什么 | 何时换 |
|---|---|---|
| **起步（S，无登录、单站点、被动即可）** | `zap-baseline.py -t <预发>`；忽略规则可暂用 `.zap/rules.tsv`（`-c`） | 无 Web 面的库/CLI **跳过**，不要为凑门禁空跑 |
| **毕业（要登录、多站点、自定义策略、告警过滤、失败门槛进计划）** | 仓内提交 `zap.yaml`，workflow 只跑 `zap.sh -cmd -autorun /zap/wrk/zap.yaml` | 出现上述任一需求就迁，不要继续堆 CLI 旗标。迁完 **删掉** `rules.tsv`，改 `alertFilter` / `passiveScan-config`，两套并行会漂 |
| **L 晋生产门** | 同一份 plan 加认证用户 +（有契约则）`openapi`/`graphql` + `activeScan`；`exitStatus.errorLevel: High` | High/Crit 不过不能晋生产。**禁止**把带 `activeScan` 的 plan 写进组织级模板套到每个仓 |

规定（与入口 N/P 无关）：

- 只打 **dev/staging/preview**，默认不打生产（主动扫描会改数据；被动扫生产也要书面批准）。
- 专用测试用户，不要用管理员 SSO 会话。
- 扫描机出网只允许目标预发与 Forgejo，避免 ZAP 变成对全网的端口扫描器。
- 报告写到挂载目录 `/zap/wrk/`（相对 plan 的路径），Actions artefact 留存；L 档摘要进看板。ZAP JSON 进 DefectDojo 前同样走 sanitizer（请求/响应里可能有会话）。
- 镜像钉 **digest**：`ghcr.io/zaproxy/zaproxy:stable@sha256:…`（平台仓维护，业务仓 `uses:` SHA）。
- 不要把 AF plan 里的 `activeScan` 当「每个 PR 都打一遍全站」；冷 PR 没有活 URL，DAST 不挡合并。

S 档被动计划（等价 baseline，仓内可直接提交）：

```yaml
# zap.yaml — 无登录、单站点、被动。有登录/多站点/主动时在此文件上加，不要另起 CLI。
env:
  contexts:
    - name: staging
      urls:
        - "${ZAP_TARGET}"          # 由 job 注入；口令走 ZAP_USER/ZAP_PASSWORD，不要写进仓
      excludePaths:
        - ".*logout.*"
  parameters:
    failOnError: true
    failOnWarning: false
    progressToStdout: true
jobs:
  - type: spider
    parameters:
      context: staging
      maxDuration: 2
  - type: passiveScan-wait
  - type: report
    parameters:
      template: traditional-json
      reportDir: /zap/wrk/
      reportFile: zap-report
  - type: exitStatus
    parameters:
      errorLevel: High
      warnLevel: Medium
```

L 档在同一文件加：context 的 `authentication` + `users`（口令仍是 env）；需要 SPA 再加 `spiderAjax`/`spiderClient`；有 OpenAPI 加 `openapi` job；认证爬完再 `activeScan`（`user:` 指向 context 用户）；已知误报用 `alertFilter`，不要在 CI 里 grep 掉。`exitStatus.errorLevel` 保持 High。

平台可复用工作流只做这一件事（业务仓把计划放仓库根 `zap.yaml`，对应容器内 `/zap/wrk/zap.yaml`）：

```bash
docker run --rm \
  -v "$PWD":/zap/wrk/:rw \
  -e ZAP_TARGET -e ZAP_USER -e ZAP_PASSWORD \
  --network <仅预发+Forgejo> \
  ghcr.io/zaproxy/zaproxy:stable@sha256:<钉死> \
  zap.sh -cmd -autorun /zap/wrk/zap.yaml
```

从打包扫描迁 AF 时，可用 `zap-baseline.py --plan-only` 先吐出一份 plan 再改，不要手抄旗标。

### 10.2 Cosign / Sigstore：可选还是必要

它管的是 **「集群里跑的镜像是不是这套 CI 签出来的」**，不管 CVE、不管密钥进日志。Trivy 过了不等于没人把别的镜像 `kubectl set image`。

| 场景 | 要不要 |
|---|---|
| S，制品只在 Forgejo 包仓库，只有这一套 CI 能推，生产人肉 helm | **可选**。先把 token、日志、Trivy 做完 |
| L，多集群 / GitOps / 要给审计看「是谁构建的」 | **必要**。构建签、准入验，缺一不可 |
| 要把镜像给别的事业部或外包集群 | **必要** |
| 内网 N、不能访问 public Sigstore（Fulcio/Rekor） | 用 **Cosign + 公司 KMS 密钥**（或自建私有 Sigstore）。不要为了 keyless 打穿内网出站 |
| 公网 P、Runner 可出站 | 可用 Sigstore keyless（OIDC 身份签发）；仍建议关键生产用 KMS 长期钥，避免依赖公共 Rekor |

落地顺序：先 `cosign sign` 写进 `build-publish.yml`（池 C），再 Kyverno/Gatekeeper `verifyImage`。只签不验等于没做。

**不能替代** ephemeral、不能替代 lockfile、不能替代 SHA 钉 Action。投毒的「爆炸半径」靠 ephemeral 和分区 Runner；Cosign 管的是**出厂铅封**。

### 10.3 开源基线、运营层、有预算后的商业

扫描器已经五件套：**Forgejo 调度 + Gitleaks + Semgrep + Trivy + Renovate + ZAP**。下面是「还要不要加平台」和「钱来了换什么」，不是再开一条并行 CI。

原则：同一类问题只留一个**合入门禁**。Sonar 和 Semgrep 不要同时挡同一条漏洞；ZAP 和 Burp 不要同时打同一预发还各挡一次。

#### A. 现在就该在场（开源基线）

| 能力 | 开源 | 必要？ |
|---|---|---|
| Git / CI / 包 | **Forgejo 16**（当前 16.0.3） | 必要 |
| 密钥 | Gitleaks（`--redact`） | 必要 |
| SAST | Semgrep | 必要（跑；阻断见 §10.1） |
| SCA / 镜像 / IaC | Trivy | 必要（合入挡 HIGH/CRIT） |
| 依赖 PR | Renovate | 修复闭环必要；MVP 可暂缺（§15） |
| DAST | OWASP ZAP（AF：一份 `zap.yaml` + `-autorun`；起步可用打包 baseline） | 有 HTTP 面则打预发；MVP 可暂缺；不挡冷 PR |

#### B. 扫描器超过三套之后（开源运营层，强烈建议）

| 能力 | 开源 | 干什么 | 何时上 |
|---|---|---|---|
| 漏洞工单 / SLA / 去重 | **DefectDojo CE** | 去重、工单、到期日。**禁止**把未消毒的 Gitleaks/Semgrep 原文入库 | 五件套齐了且 **sanitizer 测过** 再接生产流量 |
| 已发布软件的持续 CVE | **Dependency-Track** + syft 的 CycloneDX | CI 里的 Trivy 是「这次构建」；DT 是「上个月发的还在生产里的包，今天新爆了洞」 | 有稳定 SBOM 流水线之后。L 建议，S 可缓 |
| 代码质量 / 重复 / 覆盖率 | **SonarQube Community Build** | 技术债和质量门。社区版安全规则是子集，**不要当 SAST 主门**，主门仍是 Semgrep | 研发要 IDE 质量和主分支质量门时再上；与 Semgrep 分工写进规范 |

DefectDojo CE 够用：导入、去重、例外、Jira。缺的是部分 SSO/多租户体验。先 CE，审计要花报表再 Pro。

**Sanitizer（没有就不准接生产扫描）：**

```
gitleaks/semgrep JSON
  → 删除 Secret / Match / metavariable 原文（只留规则 ID、文件、行号、指纹）
  → 抽检 grep 不得出现 AKIA、ghp_、-----BEGIN
  → 才允许 DefectDojo import
```

第一次导入后查 Dojo DB/备份；搜到完整密钥 → **停导入**，先修管道。Dojo 保留期通常长于 14 天，未消毒等于把日志泄漏升级成长期密钥库。

Dependency-Track 要单独 PostgreSQL 和工人进程，别塞进 Forgejo 同机。  
Sonar 社区版许可和语言集要按当时发行说明再核一次（Sonar 对 Community / Community Build 切过品牌）。

#### C. 有安全预算之后（商业，按缺口买，不要整包换掉开源门禁）

| 缺口 | 继续用开源做门禁 | 商业补强 | 不要做的事 |
|---|---|---|---|
| 密钥监控、员工贴 GitHub 公开仓 | Gitleaks 仍挡内部仓 | **GitGuardian**、GitHub Advanced Security secret scanning | 用商业完全替换 CI 门禁导致离线就不能合代码 |
| SAST 规则维护不动、误报吵 | Semgrep CE 仍跑 | **Semgrep AppSec Platform**、**Snyk Code**、**Checkmarx One** | 不要把 Sonar + Semgrep + Checkmarx 三套都设为阻断；CodeQL 绑 GitHub，本实例用不上 |
| 依赖 CVE 噪声、许可证、恶意包 | Trivy + Renovate | **Snyk**、**Endor Labs**（可达性）、**Socket**（恶意包行为）、**Mend** / **Black Duck**（许可证治理） | 关掉 Renovate 只靠门户「周报」；OWASP Dependency-Check 仍在维护，但**不要顶 Trivy 当合入门**（见附录 A） |
| 镜像运行时 / 云姿态 / 基线 | Trivy + 内部 base | **Chainguard** 镜像；运行时 **Wiz** / Prisma Cloud | 只买扫描不换 base；CNAPP 不能替代 CI 里的 Trivy |
| DAST 认证爬深、人工渗透 | ZAP AF 计划打预发（登录/策略/过滤写进 `zap.yaml`） | **Burp Suite Professional**（人）、**Burp DAST** / **Invicti** / **StackHawk**（自动、API 向） | 用 Burp 替换 ZAP 做每次 PR 扫描（贵且慢）；也不要停在 `zap-baseline` 旗标堆上假装已认证 |
| 签名与供应链合规 | Cosign | 私有 Sigstore 交付、Chainguard Enforce | 只买咨询不接准入 |
| 给管理层的风险报表 | DefectDojo CE | DefectDojo Pro、ServiceNow VR、PlexTrac | 没有门禁只上仪表盘 |

购买顺序建议（预算到来时）：

1. **GitGuardian**（人还会把仓 push 到公网 GitHub）或 **Semgrep AppSec Platform**（规则维护/跨文件污点是瓶颈）  
2. **Burp Pro** 给安全组做人审（ZAP 自动、Burp 手工）  
3. **Socket** 或 **Snyk/Endor** 仅当恶意包或可达性 Trivy 覆盖不住  
4. **Wiz** 仅当已有多云、要云上攻击路径，不替代 CI 扫描  
5. 不要把「换商业 DAST」排在修 token 作用域和日志 redact 前面。**不要**为新栈买 Fortify / 老 Veracode 当第一套 SAST。

#### D. 和五件套怎么接

```
Gitleaks / Semgrep / Trivy / ZAP  ──sanitizer 去原文──► DefectDojo CE ──► 工单
syft SBOM ──────────────────────────► Dependency-Track ──► 已发布库存 CVE
Renovate PR ───────────────────────► 仍走 Gitleaks+Semgrep+Trivy 门禁
Cosign ────────────────────────────► 集群准入（L）
Sonar（若上）──────────────────────► 质量门，不替代 Semgrep 安全门
Burp（若上）───────────────────────► 发版前人工，不替代 ZAP 预发
```

### 10.4 包仓库策略

Forgejo 包属于 **owner（用户或组织）**，不是仓库；ACL 目前较粗（组织写权限 ≈ 能推包）。因此：

- 生产制品只推到 `company-products` 或各 BU org，**禁止推到个人用户**。
- CI 用 bot + 最小写权限。
- 启用 cleanup rules：保留最近 N 个、保留 `v*`、删除 `*-pr-*` 7 天后。
- 容器镜像用 digest 部署：`image@sha256:...`。
- L 档：构建在 Forgejo；**运行时集群只拉 Harbor / 云 Registry**（同步 + 扫描 + 不可变 tag）。原因：包 ACL 细粒度不足、生产集群不应直连 Git 控制面。

### 10.5 基础镜像

- 只允许内部 `base-images` 仓库的 hardened 镜像。
- 构建任务里 `FROM` 扫描；集群 Kyverno 拒绝外来 registry。

---

## 11. 从 CI 到运行（晋升）

```
PR 绿 ─► 合入 main ─► 构建签名制品 ─► 自动部署 dev
                              │
                              ├─► 环境测 / 预发（GitOps 改 overlay）
                              ▼
                         人工/CAB 改 prod overlay（digest）
```

- **dev**：池 C 或 GitOps 自动。
- **staging/prod**：只改 GitOps 仓。Forgejo 不持有 prod kubeconfig。
- 生产集群信任 GitOps 控制器的身份，不信任「某个 PAT」。
- 发版 tag 必须受 §7.1 保护标签约束。Writer 能推 `v*` 等于能触发本链。

S 档若没有 GitOps：允许池 C 用 OIDC 部署 **非生产**；生产用手动 `helm` 且必须贴 digest。不要把 kubeconfig 文件放进 Secrets。

---

## 12. 可用性、备份、HA 真相

### 12.1 官方事实

Forgejo Helm 文档写明：**尚未 HA 就绪**。多副本共享库和存储会出现队列/cron/缓存竞态。Chart v14 起去掉内置「看起来像 HA」的子图表，避免乐观部署。

因此：

| 档 | 控制面 | 数据面 |
|---|---|---|
| S | 单实例 Forgejo | 每日整机/卷备份 + 恢复演练 |
| L | **单活** Forgejo + 另一套冷/温备（另一 AZ），故障切换 runbook | PostgreSQL HA + 对象存储 HA + Valkey HA |

不要把 `replicaCount: 3` 写进生产清单然后宣称 99.99%。对外 SLA 按「单活 + 分钟到小时级切换」承诺。

### 12.2 备份清单（S/L 都要，频率不同）

1. PostgreSQL（含 PITR 目标）
2. 仓库存储（Git 目录或对象存储）
3. `app.ini` / Helm values / secrets 的加密副本
4. Runner 不需要备份（声明式重建）
5. 包 blob（或接受「能重建则不备」——L 档生产镜像在 Harbor，必须备 Harbor）

恢复演练：S 半年一次；L 每季度一次，写下实际 RTO。

### 12.3 升级（方案按 **Forgejo 16** 写）

生产跑 **Forgejo 16.0.3**（钉 digest）。官方（[Upgrade guide](https://forgejo.org/docs/v16.0/admin/upgrade/)）：补丁直接跟最新已发布稳定；大版本读 breaking。

| 什么 | 怎么跟 |
|---|---|
| 现在 | **16.0.3**，钉 digest。禁止浮动 `latest` 标签 |
| 16 补丁（16.0.3 → 16.0.4） | 发布后几天内上 |
| 下一稳定大版本（16 → 17） | 第一位数字变了 = breaking。预发先吃，过门禁和 CODEOWNERS/`force_merge`/OIDC `sub` 抽检再切生产；切完把本方案版本行改成 17 |
| Runner | 与 16 配套 **13.0.0**；升 17 时 Runner 同次升。13 破坏面要抽作业，不只对版本号：非法 matrix → 硬错误；表达式插值失败 → 失败；去掉 `gitea.*` 上下文和 `GITEA_` 兼容；去掉仓库 secrets 做 registry 认证 |
| 文档 | 本方案引用 [docs/v16.0](https://forgejo.org/docs/v16.0/)；升 17 后改引用并重核写死的行为 |

日历：Forgejo **16** 非 LTS，支持到 **2026-10-29**；17.0 计划 **2026-10-15**。10 月窗口吃 17，不要在 16 EOL 后还停着。

容器 + 反向代理认证：键在 **`[security] REVERSE_PROXY_TRUSTED_PROXIES`**（不是 `[service]`）。16 起镜像不再默认 `*`，必须写成反代网段。环境变量 `FORGEJO__security__REVERSE_PROXY_TRUSTED_PROXIES`。从非该网段带 `X-WebAuth-User` 应不能假冒。

订阅 https://codeberg.org/forgejo/security-announcements 。大版本前 `forgejo manager flush-queues` + 全量备份，官方有要求。

---

## 13. 可观测与审计

最小信号：

- Forgejo：登录失败、2FA、权限变更、仓库删除、Runner 注册、workflow 删除。
- Actions：失败率、排队时长、作业超时、按 org 的并发。
- Runner 主机：CPU/内存/磁盘；异常出网。
- 包：删除、覆盖（如发生）、清理规则执行。

L 档接入现有 SIEM；告警：「新注册全局 Runner」「关闭分支保护」「新的 `pull_request_target`」「OIDC sub 过宽」。

合规提问模板（三件套必须能答）：

1. 这段代码谁写的、哪次 PR、谁批的？（Git + Forgejo）
2. 这个镜像谁构建的、digest、签名？（Actions 日志 + Cosign）
3. 生产那次发布谁改了 overlay？（GitOps 仓）

---

## 14. 黄金路径（开发日常）

1. 平台开库（模板 + 保护分支 + 默认团队）。
2. 开发从 `main` 拉功能分支，推送，开 PR。
3. 池 B 跑 PR 检查（无 secrets）。
4. 他人批准（作者不能自批，已测 422）+ 敏感仓两人 + CI 绿（有 workflow 的仓才要 status check）。
5. 合入；池 A 构建；Trivy 扫镜像；推组织包仓库；写 SBOM。
6. 非生产自动；**ZAP 打预发**；生产改 GitOps digest。
7. 依赖：Renovate 开 PR，走同一套 Gitleaks/Semgrep/Trivy 门禁。

开发不直接碰 Runner、不申请云 AK、不在 YAML 里写生产地址。

---

## 15. 落地路线

平台人力 **低于 0.3 FTE** 时：只做本段 MVP，**不要**上 Dojo / ZAP / Renovate / OIDC。门禁比仪表盘重要。

勾完 **0–30 只能宣称 MVP 已上**，**不能**宣称「已上 DevSecOps」。后一档要 31–90：样例预发 ZAP、Renovate 能开 PR 且不能 merge、至少非生产 OIDC、PAT 盘点。验收清单见 §17，不要用 0–30 去勾完整张红线。

### 第 0–30 天（S 可停在这里当 MVP）

- 拉起 **Forgejo 16.0.3**（钉 digest）+ PostgreSQL + 对象存储或本地盘。容器+反代认证则显式设 **`[security] REVERSE_PROXY_TRUSTED_PROXIES`**（不是 `[service]`）。
- `[actions] LOG_RETENTION_DAYS = 14` 且 `ARTIFACT_RETENTION_DAYS = 14`（[v16.0 文档](https://forgejo.org/docs/v16.0/admin/actions/) 工件默认 90，日志默认 365）。
- 先锁定入口 **N 或 P**（或混合则两套都测），再配 DNS/`ROOT_URL`。下面 N/P 抽检是 **0–30 必测**，不是上线后再补。
- 共用：`REQUIRE_SIGNIN_VIEW`、关注册、关自建 org、SSO。未登录抽查看应无仓库。
- N：只内网/ZTNA 能访问；抽检公网 IP 连 443 应失败；Runner 与办公桌面不在同一二层。
- P：公网 443 + 全员 2FA + 登录/API 限流；抽检未登录首页无仓库；`robots.txt` 禁止收录。
- **不要新发**组织级「All 仓库」写 PAT（不发即过；全量盘点在 31–90）。
- Runner：**两个注册 + 两个标签**（`docker` / `pr-isolated`）；注册范围组织级或仓库级，**禁止全局**。若已有发布，第三标签 `release-oidc` 且无关仓抢不到。docker、非 privileged，**无公网入站**；N 档也放 CI 网段。全部 `forgejo-runner --version` = **13.0.0**。抽至少 3 条旧 YAML：`gitea.*` 上下文应失败；曾用 runner 侧 registry secret 应失败；畸形 matrix 应硬错误。
- 保护分支：approvals≥1、禁止直推；作者自批 422；**每个仓 Owner≤2，日常账号不是 Owner**。
- 有 CI 的仓才配 status check（写法见 §7.3，不要猜 `ci`）。必检 job **不要** `paths-ignore`。S 的 Semgrep **默认不**进必过；达标后改必过见 §10.1，不必升 L。
- 保护标签 `v*`，writer 推版本 tag 失败。
- 钱路/IAM/密钥：优先独立仓；拆不动见 §7.3。
- 抽检：writer `force_merge` → 405；记下管理员 `force_merge` 会 200，靠人数和审计。
- 样例仓模板带 `CONTRIBUTING.md`：纯 LGTM 不算审完（规范，不是平台开关）。
- 全库 grep 无未评审的 `pull_request_target`（16 上该事件会触发）。
- 样例服务跑通 PR 门禁（Gitleaks `--redact` + 测试 + Semgrep 不打密钥原文 + Trivy 高危）。S 未毕业：一条仅 Semgrep error、其余绿的 PR **能合**。下 artefact，`grep` 不到 AKIA / `ghp_` / `BEGIN`。
- 本实例已证伪：`permissions: contents: read` 仍能用自动 token 推非保护分支（对照 `contents: write` 同样成功，见 §9.1.1）。升 17 重测一次。
- 备份成功恢复一次。

### 第 31–90 天

- 全公司迁代码（或新项目强制）。
- 可复用 workflow；禁止业务仓私自 deploy。
- 包仓库启用；cleanup 规则。
- OIDC 到非生产云账号（即使 S 档也建议）。云 trust 按仓解码 token 的 `iss`/`sub`/`aud`，不要一份 `repo:*` glob。
- **Renovate 按 §9.1.2 上线**（独立 bot，不能 merge / 不能推 main）。没它时 Trivy 高危仍挡合入，手工升依赖一直可行；缺的是**自动开升级 PR**，不是扫描器没装。没 Renovate 是修复闭环缺口，不是门禁没装。宣称「已上 DevSecOps」仍要有它。
- 预发起来后接入 ZAP：**先** `zap-baseline`（或一份无登录的 `zap.yaml` 被动计划）；要登录/多站点/自定义策略时改成仓内 `zap.yaml` + `-autorun`，不要继续堆 CLI。
- DefectDojo **仅在 sanitizer 抽检通过后**接生产扫描。
- PAT 盘点：列出组织/仓 Secrets 与 bot 用户的 token scope（能写哪些仓、能否 merge/推保护分支）。存在 All-org 写，或 `renovate-bot` 能 merge / 推 `main` → 立刻作废。

### 第 91–180 天（进入 L 档特征）

- 发布池若上 ephemeral：上的是 **one-job 注册循环**，不是 daemon 开关（§8.3）。做不到循环就保持长驻分标签。
- Cosign + 集群准入。
- GitOps 生产。
- 权限对账、SIEM、季度恢复演练。
- 预发跟 17.0；OIDC `sub` 按仓核对（旧仓 `owner/name` vs 新仓带数字 ID）。发布作业能走 Authorized Integrations 的，收掉对应 PAT。
- 有 HTTP 面的产品仓：认证扫描写进 `zap.yaml`（登录、OpenAPI/`activeScan`/`alertFilter`/`exitStatus`）；High/Crit 阻断晋生产。不把 `activeScan` 套进组织模板。

### 不要并行做的

同时迁 Git、换 CI、换制品库、换 GitOps。顺序必须是：**Git 可访问 → CI 门禁 → 制品不可变 → 再切发布路径**。

---

## 16. 风险登记

| 风险 | 可能性 | 影响 | 处置 |
|---|---|---|---|
| 组织级万能 PAT / 自动 token 对本仓写过头 | **最高频** | job 推不该碰的仓或直推 `main` | §9.1.1–9.1.2：Renovate 专用身份；保护分支 |
| 把 `permissions:` YAML 当收回写权限 | **已证伪**（16.0.3） | `contents: read` 仍能推非保护分支 | §9.1.1：靠保护分支；提权走 Authorized Integrations |
| 管理员 `force_merge` / 删除保护规则 | **已证实** | 规则对 Owner 是建议 | Owner≤2；审计这两类 API；bot 不当 Owner |
| 多份 CODEOWNERS 或 glob 语法 | 高（已踩过） | 请求根本不出现 | 见 §7.3：一份文件 + Go 正则 |
| 有 CODEOWNERS 却没开拦正式请求 | 中 | 以为是门禁，实际是通知 | §7.3：硬门 = CODEOWNERS + `block_on_official_review_requests` |
| 状态检查写成 `ci` 等猜的名字 | 高 | job 绿了仍 405，分支锁死 | §7.3：有 CI 用 `["*"]` 或从成功 run 原样复制 |
| 组织级 `status_check_contexts: ["*"]` | 高 | 无 CI 仓永久不能合 | 分模板；无 workflow 的仓不要开 |
| Writer 能推 `v*` 标签 | 高 | 任何人触发发布链 | §7.1 保护标签；验收 writer 推 tag 失败 |
| 把 ephemeral 当成 daemon 开关 | 中 | daemon 拒绝；unless-stopped 救不回已注销的 runner | §8.3：one-job 注册循环 |
| DefectDojo 未消毒导入 | 高（已有日志事故） | 长期明文密钥库 | sanitizer 先于接入 |
| 用 0–30 勾完 §17 宣称已上 DevSecOps | 高（文档曾打架） | 未做 ZAP/Renovate/OIDC 却对外宣称 | §15 / §17：MVP ≠ DevSecOps；<0.3 FTE 只准 MVP |
| 未毕业就把 Semgrep error 设成必过 | 高 | 开箱 `p/default` 噪音 → 过几周闸被关 | §10.1：默认建议；裁规则 + owner + 周报后才阻断，不必升 L |
| Semgrep 永远建议且没 owner | 中 | 评论没人理，扫描演戏 | §10.1 毕业第 2 条：答不上谁看就不要上线，更不要假装阻断 |
| 工件默认 90 天含扫描原文 | 高 | 未 redact 的 SARIF 比日志活得更久 | §9.4：`ARTIFACT_RETENTION_DAYS = 14`（[v16.0](https://forgejo.org/docs/v16.0/admin/actions/) 默认 90）；下工件 grep |
| Integration 空 workflow/ref/event 当「已绑死」 | 高（官方空=任意） | 错仓/错文件 JWT 能写包 | §9.3：四项都填；错仓 JWT 必须失败 |
| 扫描器把密钥打进 Actions 日志 | **高频（已发生）** | 有仓权限者 14 天内可读明文 | §9.4：redact + 日志和工件都 14 天 + 不贴 PR |
| Action/依赖投毒 | 中 | 构建被劫持 | SHA 钉死 + lockfile + Trivy + ephemeral |
| 全局 Runner | 中（配错一次） | 低信任 job 与发布同机 | 禁止全局 |
| `pull_request_target` 误用 | 中 | secrets 泄漏 | 默认禁用 + Semgrep 扫 workflow |
| 容器逃逸 | **最低（无 privileged 时）** | 宿主机失陷 | privileged=false；勿优先砸预算 |
| OIDC trust `sub` 过宽 | 中 | 云账号被任意 job 领取 | 精确 sub；安全评审 |
| 官方非 HA 被当成多活 | 中 | 静默数据损坏 | replicaCount=1；备机切换 |
| 包 ACL 过粗 | 中 | 组织成员误推/恶意覆盖 | 独立制品 org + bot 推送 + Harbor 生产 |
| 第三方 Action 标签被抢 | 中 | 供应链投毒 | SHA 钉死 + 内部镜像 |
| 停在 16.0.3 之前的补丁、或 16 EOL 后不升 17 | **高（日历）** | 过支持窗口或漏安全补丁 | §12.3：Forgejo 16 钉 digest 跟补丁；10 月窗口升 17 并改方案版本行 |
| OIDC `sub` 新旧两种格式 | 中 | 云 trust 抄错，新仓换不到证或过宽 | §9.2：16 前开过 Actions 仍是 `owner/name`；16 后开或关再开是带数字 ID，不可逆。按仓解码 token |
| Runner 12.x 与 13.x 混跑 | 中 | 13 破坏性 Actions 变更，作业表现不一致 | 与 Forgejo 16 配套 **13.0.0**；禁止混跑 |
| 容器反代认证仍信 `REVERSE_PROXY_TRUSTED_PROXIES=*` | 中（16 打破默认） | 未走反代也能用 `X-WebAuth-User` 假冒 | 写成反代网段；见 §12.3 |
| Runner 与办公网同网段 | 中 | 工作流扫内网 | N/P 都把 Runner 放 CI VLAN；P 再禁公网入站 |
| P 但 `REQUIRE_SIGNIN_VIEW` 未开 | 高 | 源码被搜/被爬 | 未登录首页无仓库 |
| N 但内网匿名可看 | 高 | 扫到地址即泄源 | N 也开 `REQUIRE_SIGNIN_VIEW` + SSO |
| 误把 N 的内网信任当成授权 | 中 | VPN 失陷即全可读 | 登录与 2FA 不因在网而关 |
| P 未做登录限流/2FA | 高 | 撞库 | §6.0 P 红线 |
| 把 ZAP 打生产 | 中 | 污染数据或当成攻击 | 只打预发；生产仅只读被动监测 |
| 把打包 `zap-baseline` 当长期接口 | 中 | 登录/多站点/策略全堆在 CLI，和官方 AF 分叉 | 起步 baseline；复杂即迁 `zap.yaml` `-autorun` |
| 组织模板套 `activeScan` | 中 | 无 Web 仓空跑或打错环境 | 计划跟仓；主动扫描不进组织默认 |
| 把本方案当 IDP | 低 | 范围膨胀失败 | §2.2 |

---

## 17. 验收红线

宣称分两档。**不能**用 0–30 勾完下面整张表再写「已上 DevSecOps」。低于 0.3 FTE 只准宣称 MVP，不准宣称已上且含 ZAP/OIDC/Renovate。

| 宣称 | 必须勾完 | 谁能宣称 |
|---|---|---|
| **MVP 已上** | 「MVP 红线」+ 所选入口的「仅 N」或「仅 P」 | S 可停在 §15 0–30；平台 **<0.3 FTE** 只准这一档 |
| **已上 DevSecOps** | MVP + 「DevSecOps 红线」（§15 31–90） | 人力够做 31–90 |
| **L 档已上** | 上两项 + 「L 档另加」 | L |

先锁定入口 **N 或 P**（混合则两套都测），只跑对应「仅 N / 仅 P」。这些是 **0–30 必测**。

### MVP 红线（§15 0–30）

- [ ] 关闭注册；`REQUIRE_SIGNIN_VIEW`；未登录看不到任何仓库
- [ ] SSO；管理员 2FA
- [ ] 无全局 Runner；DB / Runner / metrics 无公网入站
- [ ] **没有发出**组织级「All 仓库」写 PAT（0–30：不发即过；全量盘点在 DevSecOps 红线）
- [ ] Gitleaks `--redact`；Semgrep 不把密钥原文打进 step 日志；工件（SARIF/JSON）`grep` 不到 AKIA / `ghp_` / `BEGIN`；`LOG_RETENTION_DAYS = 14` 且 `ARTIFACT_RETENTION_DAYS = 14`（[v16.0](https://forgejo.org/docs/v16.0/admin/actions/) 工件默认 90、日志默认 365；只查 step log 不算过）
- [ ] `main` 保护：禁止直推、`required_approvals ≥ 1`；有 CI 的仓才配 status check（**无**组织级 `["*"]`；不手填 `ci`）
- [ ] 作者自批 → 422；writer `force_merge` → 405
- [ ] 每仓 Owner/管理员 ≤ 2；日常开发与 renovate-bot **不是** Owner
- [ ] `force_merge` 与删除保护规则有审计（管理员 200 是已知绕过，不是配置错误）
- [ ] 保护标签 `v*`：普通 writer 打 `v0.0.1-test` → **422** `user not allowed to create protected tag`；白名单 = `release-bot`（空名单 = 谁都不能打）
- [ ] 全库 grep 无未评审的 `pull_request_target`（16 上该事件会触发，S/L 都禁）
- [ ] 必检 context 从一次成功 run 的 `/commits/{sha}/statuses` 抄齐，或有 CI 仓用 `["*"]`；必检 job 无 `paths-ignore`
- [ ] 钱路/IAM/密钥：**优先独立仓** + approvals=2；拆不动则 §7.3 的 CODEOWNERS + 拦正式请求（抽检非负责人 405、负责人 200）
- [ ] `CONTRIBUTING.md` 写明纯 LGTM 不算审完（规范，非平台开关；抽查 PR，**不要**写成「Forgejo 会拦」）
- [ ] 无关仓 `runs-on: [release-oidc]` 排不进发布机
- [ ] 已记录：本实例 `permissions: contents: read` **不**收回自动 token 写权限（非保护分支仍能 push；对照 `contents: write` 同样成功）。收回写权限的是保护分支，不是 YAML。不要对研发说「写了 permissions 就安全」。升 17 重测
- [ ] 合并必过 Gitleaks + 构建 + Trivy 高危。Semgrep **已接入**（跑、不打密钥原文）。S：**默认** error 为建议，不进必过——一条仅 Semgrep error、其余绿的 PR **能合**。毕业三条（规则已裁 + 有 owner + 拿得出「新增 error 误报为零」的周报，见 §10.1）之后可改必过，**仍是 S**。L：error 为必过
- [ ] 备份恢复演练有记录
- [ ] 所有 runner `forgejo-runner --version` = **13.0.0**，没有 12.x 接活。抽至少 3 条旧 YAML：`gitea.*` 上下文应失败；曾用 runner 侧 registry secret 应失败；畸形 matrix 应硬错误。13 上语义与方案「已验证子集」不一致不当绿
- [ ] 容器部署若开反代认证：`[security] REVERSE_PROXY_TRUSTED_PROXIES` 是反代网段，不是 `*`（项在 `[security]`，不是 `[service]`）。从非该网段带 `X-WebAuth-User` 不能假冒

### DevSecOps 红线（§15 31–90；没勾完不准宣称「已上 DevSecOps」）

- [ ] Renovate 能开 PR，且该身份不能绕过门禁、不能 merge、不能推 `main`（没它是修复闭环缺口，不是合入门没装；Trivy 高危在 MVP 已经挡）
- [ ] PAT 盘点：列出组织/仓 Secrets 与 bot 用户的 token scope（能写哪些仓、能否 merge/推保护分支）；无 All-org 写；`renovate-bot` 不能 merge / 不能推 `main`
- [ ] 有 Web 面的样例在预发跑过 ZAP（起步 `zap-baseline` 或无登录 `zap.yaml` + `-autorun`）
- [ ] 生产凭据不在 Actions Secrets 明文（至少非生产开始 OIDC）；云 trust 按仓解码 token 的 `iss`/`sub`/`aud`，不是一份 `repo:*` glob

### 仅 N（0–30 必测）

- [ ] 公司网外（或未过 ZTNA）访问 443 失败
- [ ] Runner 与办公桌面不在同一二层
- [ ] L：入网有身份/设备条件，不只靠共享 VPN 密码

### 仅 P（0–30 必测）

- [ ] 全员 2FA（不只管理员）
- [ ] 登录/API 限流；S 有反代限流，L 有 WAF + SIEM
- [ ] 未登录首页无仓库；`robots.txt` 禁止收录
- [ ] Git 以 HTTPS+token 为主；若开公网 SSH 则密钥-only 且非 22

### L 档另加（N/P 都要）

- [ ] 三级 Runner 池；若 ephemeral 则是 one-job 注册循环（daemon 拒 ephemeral）
- [ ] 无 fork CI
- [ ] DefectDojo 仅经 sanitizer；库内 grep 不到完整密钥
- [ ] 生产镜像 digest + 签名 + 准入
- [ ] 生产部署只走 GitOps
- [ ] OIDC `sub` 精确到这一仓（按 16 实际格式：旧仓 `owner/name` 或新仓带数字 ID）和 ref；`iss` 含 `/api/actions`。验的是 **云 IdP 配置**（解码一枚 token），不在 Forgejo UI
- [ ] 写包/打 tag/跨仓 API 走 Authorized Integrations，不靠扩 `permissions:` 或组织 PAT。每条 Local Integration 打开看：Source Repository **必选**（官方）；workflow 文件名 / git ref / Event **官方允许空=任意，本方案四项都填**。用**另一仓或另一 workflow 文件**要 JWT 调写包 API 必须失败
- [ ] 权限季度对账；SIEM 能追三次发布
- [ ] 书面 RTO/RPO 与最近一次演练结果一致
- [ ] `replicaCount` 仍为 1，且有切换 runbook
- [ ] ZAP 认证扫描是仓内 `zap.yaml`（登录 + `exitStatus` High），对预发 High/Crit 阻断晋生产；不是加长的 `zap-baseline` 命令行

---

## 18. 关键决策

1. **一套架构、两档强度**，避免中小企业抄大型企业拓扑、大型企业用 Compose 装完就停。
2. **方案按 Forgejo 16 写**（当前 **16.0.3**，Runner **13.0.0**）。钉 digest，跟 16.0.x 补丁；下一稳定大版本预发验证后升，并改本方案版本行。Authorized Integrations 是 16 的正式提权路径。
3. **入口两种都写进方案：N 内网/零信任，P 公网须登录。** 共用禁止匿名；P 多登录面防护，N 多网络门和横向隔离。不把「在内网」当成已经授权。
4. **扫描栈固定为 Gitleaks + Semgrep + Trivy + Renovate + ZAP**。ZAP 长期用 **Automation Framework**：一份 `zap.yaml` 描述目标/登录/爬取/被动或主动/报告/失败；起步可用打包 `zap-baseline`，规则变复杂再 `-autorun`。Cosign 在 L / 多集群为必要。DefectDojo 必须先 sanitizer。平台 <0.3 FTE 则停在 MVP（**停在 MVP ≠ 已上 DevSecOps**）。没 Renovate 是修复闭环缺口，不是合入门没装。S 的 Semgrep 默认建议；毕业后可阻断，**不必升 L**（判据 §10.1）。
5. **事故序：过宽 token > 密钥进日志 > 依赖投毒 > 容器逃逸。** 全局 Runner 和宽 PAT 分开治。Sonar / Dependency-Track / Burp 按缺口加，不替代门禁。
6. **承认非 HA**：用数据面 HA + 单活控制面 + 演练过的切换，不承诺多活。
7. **安全不内生于 Forgejo**：强制点在保护分支和集群准入；工具可替换。
8. **凭证与日志优先于逃逸预算**：扫描器加再多，一个组织级 PAT 或未 redact 的日志就能清零。
9. **生产身份用 OIDC，不用 PAT**。
10. **Forgejo 包仓库作源，生产运行时拉专用 Registry**（L）；S 档可以只用 Forgejo OCI。
11. **可复用 workflow 集中在 `company-platform`**，业务仓没有生产 kube 权限。
12. **审查以本实例实测为准（细节只在 §7.3）：** 作者自批 422。保护规则硬约束 writer；Owner 可用 `force_merge` 或删规则绕过。CODEOWNERS 能用；硬门 = 一份 Go 正则文件 + 拦正式请求。钱路优先拆仓，拆不动用这条。有 CI 的仓 status check 用 `["*"]` 或从成功 run 复制全名，不要写 `ci`。无 CI 仓不要开。纯 LGTM 是规范不是开关。
13. **Renovate 与发布机器人两套身份**；禁止用「一人一仓」硬套 Renovate。`permissions:` YAML **已证实不是控制**（16.0.3：`contents: read` 仍能 push 非保护分支）。
14. **发布 Runner 用独立标签**；无关仓抢不到。组织级注册不够时改为仓库级。

---

## 19. 实施时按仓落地的最小文件集

每个产品仓：

```
.forgejo/workflows/ci.yml          # 只调用 platform 可复用工作流
CONTRIBUTING.md                    # 纯 LGTM 不算审完
.gitleaks.toml
.semgrep.yml
renovate.json
zap.yaml                           # ZAP AF 计划（毕业形态）；起步可暂用打包 baseline
.zap/rules.tsv                     # 仅 baseline 过渡。迁 AF 后删
CODEOWNERS                         # 仅路径门禁仓：根目录一份、Go 正则；改忽略文件也要过负责人（§7.3）
Dockerfile                         # FROM 仅内部 base
```

平台仓：

```
.forgejo/workflows/reusable-ci.yml
.forgejo/workflows/reusable-build.yml
.forgejo/workflows/reusable-dast-zap.yml   # docker + zap.sh -cmd -autorun；镜像钉 digest
actions/checkout-mirror/           # 钉 SHA 的镜像说明
docs/oidc-trust.md                 # 各云账号 trust 条件
```

基础设施仓（L）：

```
clusters/prod/kustomization.yaml   # 只引 digest
policy/kyverno-signed-images.yaml
```

---

## 20. 与「更大平台」的关系

若公司同时建设内部开发者平台（门户、环境、GitOps 控制面），Forgejo 只担任：

- 源码与评审系统
- Actions 调度
- 内部包的源站

门户去调 Forgejo API，不要在 Forgejo 里长出环境管理。Runner 不要变成通用作业平台。边界清楚，两个系统才都活得下来。

---

## 21. 红队问题 → 正文规定

| 问题 | 规定 |
|---|---|
| Renovate 与「一人一仓 PAT」打架 | §9.1.2 两套 bot 身份：Renovate 可开 PR，不能 merge / 推保护分支 / 写包 |
| `permissions:` YAML 当控制 | §9.1.1 **已证伪**：键被解析、被忽略。收回写的是保护分支 |
| S 兼职撑不住五件套 | §5 / §15 / §17：低于 0.3 FTE 只做 MVP，不上 Dojo/ZAP/Renovate/OIDC；勾完 0–30 只能宣称 MVP |
| S Semgrep 黄灯能否合 | §10.1：默认建议（规则集误报不像 Gitleaks/Trivy）；毕业三条后可必过，不必升 L。测法：未毕业时仅 error 的 PR 能合 |
| 没有 Renovate 算不算没上门禁 | §15 / §17：Trivy 高危已挡合入；缺的是自动开升级 PR。没它是闭环缺口，31–90 才宣称已上 |
| 密钥窗口只收紧日志 | §9.4：工件默认 90 天，一并改 14；下 artefact grep |
| Runner 13 只对版本号 | §12.3 / §17：抽旧 YAML（`gitea.*`、registry secret、畸形 matrix） |
| Integration 空字段当绑死 | §9.3：官方空=任意；本方案四项都填；错仓 JWT 必须失败 |
| Dojo 变成长期密钥库 | §10.3 sanitizer 先于接入；抽检失败停导入 |
| 大 org 发布机被乱调度 | §8.3 独立标签 `release-oidc`；无关仓抢不到 |
| 管理员 `force_merge` / 删规则 | Owner≤2；审计这两类操作；bot 不当 Owner |
| CODEOWNERS 未复现 / 只是通知 | **已更正** §7.3：配错导致；硬门 = 一份 Go 正则 + 拦正式请求。钱路仍优先拆仓 |
| 状态检查写成 `ci` | §7.3：格式 `workflow / job (event)`；有 CI 用 `["*"]` 或从成功 run 复制 |
| 组织级 `status_check ["*"]` | 只给有 workflow 的仓；文档仓不要开 |
| Writer 打版本 tag | §7.1 保护 `v*` |
| ephemeral 当 daemon 开关 | §8.3：one-job 注册循环；daemon 拒 ephemeral |
| `permissions:` / 自动 token 不够还发 PAT | §9.3：16 上 Authorized Integrations 是正式提权路径（写包/打 tag/跨仓 API），替代自动 token 和 `permissions:` |
| OIDC `sub` 抄一份套全公司 | §9.2：新旧仓两种格式，按仓解码 token |
| Runner 12 与 13 混跑 | 封面 / §12.3：Forgejo 16 配套 Runner 13.0.0 |
| 16 容器反代认证沿用 `*` | §12.3：键在 `[security]`，写成反代网段 |
| ZAP 停在打包 baseline / CLI 旗标 | §10.1.1：官方 AF 为主路径；起步 baseline，复杂即 `zap.yaml` `-autorun`；`activeScan` 不进组织模板 |

---

## 附录 A. 名词与产品地图（2026-08）

给研发和安全同一张表：每个词看什么、看不到什么、本方案用谁、钱来了换谁。产品按 **2026 仍在用、有社区或市场份额的** 列；过时或不适配合入门禁的标「不要」。升大版本后产品名会变，买之前再核一次官网。

### A.1 先分清层（不要用一个词概括全部「安全扫描」）

| 层 | 英文 | 输入 | 能看到 | 看不到 | 本方案 |
|---|---|---|---|---|---|
| 密钥扫描 | Secret scanning | Git 历史 / diff | 私钥、云密钥、token 原文 | 逻辑漏洞、CVE | **Gitleaks** 合入门 |
| 静态应用安全测试 | **SAST** | 源码（不跑起来） | 注入、不安全 API、硬编码、危险 workflow | 运行时配置、鉴权是否真生效、依赖 CVE | **Semgrep CE** 合入门 |
| 软件成分分析 | **SCA** | lockfile / 清单 / 镜像层 | 已知 CVE、过期包、许可证 | 你们自己的代码写错 | **Trivy** 合入门 |
| 基础设施即代码 | **IaC scanning** | Dockerfile、K8s YAML、Terraform | 特权容器、公开桶、弱网络策略 | 集群里实际跑着的状态 | **Trivy** config，L 必过 |
| 容器 / 镜像扫描 | Container scanning | 构建后的 OCI | 基础镜像和包 CVE | 运行中逃逸、编排错误 | **Trivy image**，构建后 |
| 动态应用安全测试 | **DAST** | 已部署的 HTTP | XSS、CSRF、头缺失、未授权接口 | 没爬到的路径、纯库/CLI | **ZAP** AF，只打预发 |
| 软件物料清单 | **SBOM** | 构建产物 | 「这版镜像里有哪些包」 | 包今天新爆的洞（要另有库存扫描） | **syft** → CycloneDX，L 归档 |
| 签名与准入 | Signing / provenance | 镜像 digest | 是不是这套 CI 签出来的 | CVE、密钥进日志 | **Cosign**，L 必要 |
| 依赖更新 | Dependency update | 清单文件 | 过期依赖的 PR | 不替代漏洞判定 | **Renovate** 开 PR，走上门禁 |
| 漏洞运营 | ASPM / VR | 各扫描器报告 | 去重、SLA、例外 | 不能替代合入门 | L：**DefectDojo CE**（先 sanitizer） |
| 已发布库存 CVE | Continuous SCA | SBOM 库存 | 上个月发的包今天新洞 | 这次构建没扫到的 | L：**Dependency-Track** |
| 云 / 运行时姿态 | **CNAPP** / 运行时 | 云账号、集群 | 暴露面、攻击路径、运行时 | 替代不了 CI 里的 SAST/SCA | L 可选 **Wiz**；不进合并门 |

同一类问题 **只留一个合入门**。Sonar 不和 Semgrep 抢同一条漏洞；ZAP 不和 Burp 各挡一次预发。

### A.2 名词详解

**SAST（Static Application Security Testing）**  
不运行程序，按源码/AST/数据流找缺陷。快，适合每个 PR。误报来自「这条路径实际走不到」，且跟规则集走。本方案：Semgrep CE；S 默认建议，毕业后可必过（不必升 L）；L 默认必过。跨文件污点（用户输入一路跟到 sink）CE 弱，这是买 Semgrep AppSec Platform 的理由，不是再买第二套 SAST。

**污点分析（taint）**  
从「不可信输入」跟到「危险操作」（SQL、exec、模板）。**单函数 / 文件内跨函数 / 跨文件** 不是一回事。Semgrep CE：单文件、单函数。OpenGrep：单文件、跨函数。跨文件仍是 Semgrep AppSec Platform / CodeQL / Checkmarx One。对照见 A.2 OpenGrep。

**DAST（Dynamic Application Security Testing）**  
打**活着的** HTTP。被动：只看响应头和爬到的页面（接近 `zap-baseline`）。主动：真发攻击 payload（`activeScan`，只打有授权的预发）。认证扫描 = 先登录再爬，否则只能看到登录页。本方案：ZAP Automation Framework，仓内 `zap.yaml` + `-autorun`。

**IAST（Interactive）**  
在运行的应用里插桩，结合代码位置和真实请求。信号好、接入重（要改运行方式）。S 不上。L 有专职 AppSec 且能改预发部署再评估 **Contrast**；不替代 ZAP 预发门。

**SCA（Software Composition Analysis）**  
看**别人的包**有没有已知洞和许可证问题。靠 lockfile / SBOM，不是「猜 import 名」。Trivy 扫这次构建；Dependency-Track 扫已发布库存。**可达性（reachability）**：CVE 在依赖树里，但你们的代码调不到那函数 → 噪声。要降噪买 **Endor Labs** 或 Snyk 的可达性，不要关 Trivy。

**SBOM**  
一份「这版制品含哪些组件」的清单。常用 **CycloneDX**（安全/库存）和 **SPDX**（许可证/合规）。有 SBOM 不等于已扫描；要把 SBOM 交给 Trivy/DT 才会变成洞列表。

**密钥扫描 vs SAST**  
密钥是「仓库里出现了不该出现的凭据」。Gitleaks 专门干这个且必须 `--redact`。Semgrep 也能配密钥规则，但本方案密钥类以 Gitleaks 为准，避免两套都把原文打进日志。

**IaC 扫描**  
Dockerfile/K8s/Terraform 的**声明**误配（`privileged: true`、`:latest`、公开 22）。不是云上此刻的真实状态（那是 CSPM/CNAPP）。

**容器扫描 vs 运行时**  
镜像扫描：构建产物里的包 CVE。运行时：进程异常、逃逸、云错误配置。Falco 是主机/K8s 运行时；**Wiz** / Prisma 是云上姿态。都不能替代 Trivy image。

**CVE / CWE / CVSS / GHSA / OSV**  
CVE：公开漏洞编号。CWE：缺陷类型（如注入）。CVSS：0–10 分，本方案门禁用 HIGH/CRIT，不把 4.0 当阻断。GHSA：GitHub 安全公告。OSV：开源漏洞交换格式。Trivy 会聚合这些源。

**误报 / 漏报**  
误报：报了但不可利用（合入被吵死）。漏报：真有洞没报（更危险）。门禁要少而准；其余进 DefectDojo 当工单。例外必须有过期日。

**合入门 vs 建议 vs 晋生产门**  
合入门：挡 `main`。建议：PR 评论，不合失败。晋生产：预发 ZAP High/Crit、镜像签名。DAST **不挡冷 PR**（没有活 URL）。

**ASPM**  
把多扫描器结果收成工单/SLA，不是扫描器。本方案开源用 DefectDojo CE。商业还有 Semgrep 平台自带的分诊、Snyk AppRisk、ServiceNow VR。没有门禁只上 ASPM 是报表演戏。

**CNAPP**  
云账号里的工作负载、身份、网、CVE 拼成攻击路径。2026 主流是 **Wiz**、Prisma Cloud、Orca。**不**当源码合入门，也**不**替代 SCA。

**SLSA / provenance**  
「这镜像是哪次构建、哪份源码、哪套 CI 产的」的证明。Cosign 签的是摘要；Kyverno 验的是签名。不验 = 没做。

**依赖投毒 / 错名包（typosquat）**  
CVE 扫描看不到「包是恶意的但还没有 CVE」。要行为分析：**Socket**。 Renovate 乱升级到恶意版本 = 自己把门打开，所以 Renovate PR 必须过 Gitleaks/Semgrep/Trivy，且 bot 不能 merge。

**许可证合规**  
GPL 进专有产品等。Trivy 能做基础许可检测；审计向的深度用 **Black Duck** 或 FOSSA。L 档合入拒绝名单写进门禁。

**模糊测试（fuzzing）**  
随机/变异输入砸解析器、协议、加密。适合编解码、自研协议。OSS：go-fuzz、libFuzzer、clusterfuzzlite。不是 Web DAST，S 默认不上。

**CodeQL**  
GitHub 的语义查询引擎，SAST 里深度好。免费公共仓、商业在 GitHub Advanced Security。**Forgejo 不是 GitHub**，本实例不把它当门禁。不要为了 CodeQL 把源码镜像到公开 GitHub。

**OpenGrep**（参考，不是第二套门禁）  
2025-01 从 Semgrep CE 分出的引擎（LGPL-2.1），Aikido / Endor / Orca 等厂商养着，把 CE 收到付费里的**文件内跨函数污点**留在开源。规则格式大体兼容，CLI 已开始分叉。第三方文案常写成「跨文件」——**不对**。以 Semgrep 自己 2026-08 的对比为准：

| | Semgrep CE（本方案门禁） | OpenGrep | Semgrep AppSec Platform |
|---|---|---|---|
| 钱 | 免费 | 免费 | ≤10 人免费，再按人收费 |
| 污点 | 单文件、**单函数** | 单文件、**跨函数**（`--taint-intrafile`） | **跨文件 + 跨函数** |
| 规则 | 社区注册表 | 自带/自写；官方规则许可已收紧 | 社区 + Pro + 分诊 |
| 产品 | CLI | 仍是 CLI（厂商拿它当引擎） | 仪表盘、SCA、Secrets |
| 往上走 | 同一条线升 Platform | **没有**官方升级路径 | 就是这条线 |

评价：引擎一年下来速度和文件内多跳污点比 CE 好；当「组织 SAST 产品」弱（没有 Registry/策略层）。**不必换。** 痛的是文件内跨函数、又不买平台 → 拿一个仓对照跑，值再换，与 CE **二选一**。痛的是跨文件/分诊 → 买 Platform。不要两套都挡合并。

### A.3 按能力：开源门禁、商业补强、不要用的

**不要**当 2026 新栈首选（落后、错层、或会把门禁弄乱）：

| 不要 | 原因 |
|---|---|
| OWASP Dependency-Check **顶** SCA 门 | 项目还在（OWASP Flagship，2026-05 仍有 12.2.x），**不是死了**。慢（NVD API key、CI 要缓存）、匹配偏 CPE→NVD（误报多、易漏 GHSA）、不做镜像+IaC。2026 开源 CI 的默认已经是 **Trivy / Grype**。本方案合入门 Trivy；Java 要 NVD HTML 可以另跑，不要双门 |
| tfsec 单独再跑一遍 | 已并进 Trivy；两套 IaC 双门 |
| Fortify、老 Veracode 当第一套 SAST | 面向遗留/二进制/COBOL；新语言栈又慢又贵 |
| SonarQube Community 当 SAST 主门 | 社区版安全规则是子集；质量门可以，安全门仍 Semgrep |
| OpenVAS / 端口扫描当 DAST | 扫主机端口，不是 Web 应用 |
| Qualys WAS 当每次 PR 的 DAST | 企业外网扫描器，不适合 Forgejo 预发流水线 |
| Dependabot | GitHub 专用；本实例用 **Renovate** |
| 只买 CNAPP（Wiz）关掉 Trivy | 云上可见 ≠ 这次构建没 CVE |

#### 密钥

| | 产品 | 角色 |
|---|---|---|
| 开源门禁 | **Gitleaks**（`--redact`） | 每个 PR / `main` |
| 开源补充 | TruffleHog | 历史深挖、验证密钥是否还活；不要和 Gitleaks 双门 |
| 商业 | **GitGuardian** | 公网 GitHub/员工泄露、全历史、组织级 |
| 商业（绑 GitHub） | GitHub Advanced Security secret scanning | 人把仓 mirror 到 github.com 才有意义 |

#### SAST

| | 产品 | 角色 |
|---|---|---|
| 开源门禁 | **Semgrep CE** | 快、规则像代码、适合 Forgejo Actions |
| 开源（不要当第二门） | Bandit / gosec / Brakeman | 单语言；已被 Semgrep 规则覆盖则不要再挡一次 |
| 开源分叉（参考） | OpenGrep | 文件内跨函数污点；与 CE 二选一，不并行。跨文件仍要 Platform |
| 商业首选 | **Semgrep AppSec Platform** | 跨文件污点、Pro 规则、AI 分诊、策略 |
| 商业 | **Snyk Code** | IDE 体验、和 Snyk SCA 同一门户 |
| 商业（大企业平台） | **Checkmarx One** | 深污点、合规仪表盘；不要和 Semgrep 双阻断 |
| 不作为本实例门禁 | CodeQL | 要 GitHub |

#### SCA / 恶意包 / 许可证

| | 产品 | 角色 |
|---|---|---|
| 开源门禁 | **Trivy** | 依赖 + 镜像 + IaC 一个二进制 |
| 开源补充 | **Grype** + **syft** | 自建 SBOM 流水线；与 Trivy 选一个做阻断 |
| 开源漏洞库查询 | OSV-Scanner | 可作核对，不作第二门 |
| 更新机器人 | **Renovate** | 开 PR，不能 merge |
| 商业开发者体验 | **Snyk Open Source** | 修法 PR、IDE |
| 商业可达性 | **Endor Labs** | 降 CVE 噪声 |
| 商业恶意包 | **Socket** | 行为/错名/维护者被劫持；CVE 扫描看不到 |
| 商业许可证治理 | **Black Duck**、FOSSA、Mend | 法务/收购尽调；L 有专有产品+GPL 风险时 |

#### DAST / 人工

| | 产品 | 角色 |
|---|---|---|
| 开源门禁 | **ZAP**（Automation Framework，`zap.yaml` + `-autorun`） | 预发；起步 baseline |
| 开源补充 | Nuclei | 模板化已知漏洞；补 ZAP，不替代 |
| 商业人工 | **Burp Suite Professional** | 安全组发版前人手 |
| 商业自动（API 向） | **StackHawk**、**Invicti**、Burp DAST | 认证 API、OpenAPI；贵，按缺口买 |

#### 镜像、供应链、云

| | 产品 | 角色 |
|---|---|---|
| 开源 | **Trivy image**、**syft**、**Cosign** | 扫、清单、签 |
| 开源准入 | Kyverno / Gatekeeper | 集群验签、禁 `:latest` |
| 商业镜像 | **Chainguard** | 少 CVE 的基础镜像；比「再买一个扫描器」有效 |
| 商业 CNAPP | **Wiz**（2026 主流）、Prisma Cloud | 多云攻击路径；L、已有云账 |
| 运行时（K8s） | Falco | 主机侧；最低优先级（事故序） |

#### 运营与质量（不是合入安全门）

| | 产品 | 角色 |
|---|---|---|
| 开源 ASPM | **DefectDojo CE** | 去重工单；必须 sanitizer |
| 开源库存 | **Dependency-Track** | 已发布 SBOM 的持续 CVE |
| 开源质量 | **SonarQube Community Build** | 重复、覆盖率、风格；**不是** SAST 主门 |
| 商业质量/安全规则 | SonarQube Developer/Enterprise | 已用 Community 质量门再加 |
| 商业工单 | DefectDojo Pro、ServiceNow VR | 报表/ITSM |

### A.4 和本方案五件套的对应（避免买重）

```
密钥     Gitleaks          → 钱：GitGuardian（公网泄露）
SAST     Semgrep CE        → 钱：Semgrep AppSec Platform 或 Snyk Code（二选一）
SCA/镜像/IaC  Trivy        → 钱：Socket（恶意包）或 Endor（可达性）；许可：Black Duck
更新     Renovate          → 不要换成「门户周报」
DAST     ZAP AF            → 钱：Burp Pro（人）± StackHawk/Invicti（API 自动）
SBOM     syft              → L：Dependency-Track
签名     Cosign            → L：集群准入；镜像：Chainguard
运营     DefectDojo CE     → 钱：Pro / ITSM
云姿态   （无门禁）        → L：Wiz；不关 Trivy
```

S 档：附录里所有「商业」都可以没有。L 档：按缺口买一行，禁止并行三套 SAST。

---

## 修订

| 日期 | 说明 |
|---|---|
| 2026-08-27 | 初版。能力数字按当日官方文档与 Helm HA 声明核对。 |
| 2026-08-27 | 补 ZAP；暴露面改为公网可达但必须登录（`REQUIRE_SIGNIN_VIEW`）。 |
| 2026-08-27 | 入口拆成 N（内网/零信任）与 P（公网须登录）两等公民，与 S/L 正交。 |
| 2026-08-27 | 事故概率序；token/日志硬化；Cosign 可选性；DefectDojo/DT/Sonar 与商业升级路径。 |
| 2026-08-27 | §7.3：禁止自批、敏感路径 CODEOWNERS（不用 protected_file_patterns）、LGTM 为规范。 |
| 2026-08-27 | 闭环 r1/r2：Renovate 双身份、permissions 非控制、S 人力门槛、Dojo sanitizer、发布标签隔离、CODEOWNERS 门禁/自身/计分、break-glass runbook。 |
| 2026-08-27 | 以本实例实测改 §7.3：force_merge 绕过 apply_to_admins；删规则 204；CODEOWNERS 四位置未生效故撤出门禁；status_check * fail-closed。 |
| 2026-08-29 | ZAP：官方主推 Automation Framework（一份 YAML plan + `-autorun`），会逐步取代命令行+打包扫描。方案改为起步 baseline、复杂即迁 `zap.yaml`。 |
| 2026-08-29 | CODEOWNERS：官方理论是自动请求审查（不是必批）；本实例四位置未复现；用之前必须自己验。 |
| 2026-08-29 | 基线改为正在用的 **Forgejo 16.0**（不看 15）。Authorized Integrations / OIDC `sub` 双格式 / Runner 13 / 非 LTS 到 2026-10-29 写入正文。 |
| 2026-08-29 | 版本策略改为 **跟当时最新稳定**（核实：Forgejo 16.0.3、Runner 13.0.0）。钉 digest，不钉 LTS，不用浮动 `latest`。 |
| 2026-08-29 | 方案正文明确写 **Forgejo 16**（16.0.3），引用改回 v16.0 文档；升 17 时改版本行。 |
| 2026-08-29 | 附录 A：SAST/DAST/SCA 等名词 + 2026 开源/商业对照（Semgrep 平台、ZAP AF、Trivy、Socket、Endor、Wiz、Burp）；过时产品不进推荐。 |
| 2026-08-29 | 附录 A：OpenGrep 与 Semgrep 对照作参考（文件内跨函数 ≠ 跨文件；不必换门禁）。 |
| 2026-08-29 | QA 实测更正 §7.3：CODEOWNERS 能用，硬门=拦正式请求；status check 真名是 `workflow / job (event)`；保护标签 `v*`；ephemeral 是 one-job 循环。其余只写「见 §7.3」。 |
| 2026-08-29 | 审查报告：`docs/2026-08-29-scheme-review-cc.md`。补：根目录唯一 CODEOWNERS、`paths-ignore` 锁死、ZAP 禁用 `workflow_run`、`pull_request_target` 进 S 验收、忽略文件走 CODEOWNERS。 |
| 2026-08-29 | grokbot QA：`docs/2026-08-29-scheme-review-grok.md`。§17 拆 MVP / 已上 DevSecOps；S Semgrep 黄灯能合；PAT 盘点在 31–90；工件 14 天；Runner 13 抽作业；AI 空=任意须验；N/P 为 0–30 必测。CODEOWNERS 硬门不按该报告纸面回退。 |
| 2026-08-29 | `permissions:` **已证伪**（§9.1.1）：`contents: read` 与 `contents: write` 都能推非保护分支。§18 决策 13 改为「已证实不是控制」。CODEOWNERS 位置隔离：根目录唯一一份，硬门 405/200 仍成立。 |
| 2026-08-29 | §15 0–30 补齐 §17 MVP 四条：grep `pull_request_target`、必检 job 无 `paths-ignore`、`CONTRIBUTING.md` LGTM、禁止全局 Runner。`ARTIFACT_RETENTION_DAYS` 默认 90 按 [v16.0 文档](https://forgejo.org/docs/v16.0/admin/actions/) 复核，不再单靠 grokbot。 |
| 2026-08-29 | Semgrep 默认建议与升 L 脱钩：毕业 = 规则已裁 + 有 owner + 拿得出「新增 error 误报为零」的周报。Renovate：没它是修复闭环缺口，不是门禁没装。 |
| 2026-08-29 | 扫漏改：§3.2 仍写 Semgrep「error 级阻断」；§10.1 表未写毕业；§10.3 把 Renovate/ZAP 写成无条件必要。三处改成与 §10.1 / §15 一致。 |
