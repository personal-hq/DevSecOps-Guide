# 门禁 QA 检查清单

**清单本身按「绕过路径」而不是「工具」组织——这个轴是对的。** 定案能挡住
「普通开发者往 main 塞未扫代码」，但挡不住：谁能关闸、闸没跑算不算过、
发版是不是另一条路、忽略文件是不是后门。

> **本文所有 ✅/❌ 标注均为在 Forgejo v16.0.3 上的实测结果**；完整证据表在
> [`README.md` §三 分支保护](README.md#三分支保护全部实测)，此处只留结论和动作。
> **有三条通行做法在 Forgejo 上是错的**，照做会得到虚假保障——见下文 ⚠️ 节。

---

## ⚠️ 先看这三条：通行做法在 Forgejo 上不成立

### 1. 「打开 Apply to admins 就能防管理员强合」—— 挡不住

`force_merge` 是合并 API 的独立布尔字段，**`apply_to_admins` 管不到**：管理员开着它
照样 200 绕过；更彻底的是管理员可以直接 `DELETE` 掉整条规则（`204`）。write 协作者
则被正常拦住（`405 Does not have enough approvals`）。

> **控制点不是某个开关，是「谁是仓库管理员」。** 保护规则完整约束 writer，对
> owner/管理员是建议性的。要防有意绕过靠权限设计 + 审计，不是勾选框。

### 2. 「把 `.forgejo/workflows/**` 放进 Protected file patterns」—— 会锁死

`protected_file_patterns` 的语义是**冻结**，不是「需要更多人审」：直推 `403 path is
protected`，PR 合并 `405 Changed protected files`。结果是**谁都改不了 workflow，
正规 PR 也不行**。

**要「改 workflow 需额外人审」，正确工具是 CODEOWNERS + `block_on_official_review_requests`**——
非负责人批准仍被拦，负责人批准才放行（实测闭环见
[README.md](README.md#codeowners此前的未复现是环境配置错误)）。两个坑一起踩会让人
误判成「Forgejo 不支持 CODEOWNERS」：**只在仓库根目录放一份**（`.gitea/` 是上游兼容
路径，`docs/` `.forgejo/` 也合法——但那是四个制造冲突的机会，不是四个选项），
**语法是 Go 正则不是 glob**。

### 3. 「必检 context 用 job 名」—— 名字格式不是你想的那样

Forgejo 上报的是 **`<workflow 名> / <job 名> (<事件>)`**：

```
保护规则里写的：  ['gate-check']
实际上报的：      'gate / gate-check (pull_request)'
```

workflow 文件**没写 `name:`** 时前半截是空的，context 变成 `/ no-checkout (push)`——
以斜杠开头，凭直觉绝不可能猜到。

**写错的后果不是「门禁失效」，是「永久无法满足」**——job 跑成功了照样 405。
验收方法：`GET /repos/{owner}/{repo}/commits/{sha}/statuses`，逐字抄 `context` 字段。

---

## A. 门禁是否真的挡住合并

- [ ] `main` / 长期 `release/**` 都有保护规则；禁止直推
- [ ] ~~`Apply to admins` 已打开~~ → **见上文第 1 条，这条挡不住 `force_merge`**。
      改为：**收紧仓库管理员名单** + 审计管理员合并行为
- [ ] 必检 context 名字**逐字**取自 `/commits/{sha}/statuses` 的实际上报值
      （格式 `workflow / job (event)`，见上文第 3 条）
- [ ] 必检 job **禁止** `continue-on-error: true`；扫描器崩溃/超时/镜像拉不下来 = 失败不是绿
- [ ] **不要对必检 job 用 `paths-ignore`** —— 被跳过的 job **从不上报 status**，
      于是「只改文档」的 PR 永久合不了（`405 Not all required status checks successful`）。
      Forgejo 是 **fail closed**，不存在「跳过却上报 success 放行」这种情况。
      同理 `status_check_contexts: ["*"]` 在无 CI 的仓库上永久卡死，**不能组织级统一套用**。

- [ ] 作者不能给自己的 PR 凑满审批 —— ✅ 平台已强制：`422 approve your own pull is not allowed`。
      **但 `required_approvals: 0` 时这条等于不存在**（作者不能 Approve，但可以直接合）
- [ ] `dismiss_stale_approvals` 打开 —— **不开的话必需审查完全形同虚设**：
      提干净 PR → 拿审批 → 再推任意代码 → 直接合并
- [ ] 改 workflow 的 PR 要额外人审 → **用 CODEOWNERS，不要用 protected_file_patterns**（见上文第 2 条）

## B. 扫描覆盖有没有空档

- [ ] Gitleaks 扫的是**全 git 历史**不只是工作区；allowlist 与 `.gitleaksignore` 有人审
- [ ] **Semgrep 规则集是浮动的**——`--config p/xxx` 引用的是 semgrep.dev 上的在线
      规则库，规则内容会在上游变化，且扫描时依赖外部可达。要可复现就把规则文件放进
      仓库或钉版本。**`--config auto` 还会把项目 URL 发到 semgrep.dev**，内部服务器
      要评估这条数据外流（见 [../30-security-scanning/tool-selection.md](../30-security-scanning/tool-selection.md)）。

- [ ] Trivy fs（PR）含 lockfile、Dockerfile、Helm/K8s/Terraform；多模块路径都扫到
- [ ] Trivy image 在**最终镜像最后一层写完之后**扫；digest 钉死再推 Registry；
      禁止先推后补扫、禁止把 `latest` 当唯一引用
- [ ] base image 与 action 本身也是 digest；CI 里有一步 grep 校验没有 `@v1` / `@latest` / 未钉 sha256
- [ ] Renovate 的安全补丁 PR 仍走同一组必检 + 评审；automerge 范围有书面限制

## C. 忽略文件是不是合法豁免

- [ ] `.trivyignore` / `.semgrepignore` / `.zap/rules.tsv` / gitleaks allowlist
      **本身受保护**（用 CODEOWNERS 要人审，不是 `protected_file_patterns` 冻结）
- [ ] CI **解析并强制**「原因 + 到期日」；过期或格式不对 = job 失败

  > **制度写了不等于执行了。** 没有 CI 校验的「必须写到期日」是纯自觉。

- [ ] 同一 PR 里「引入漏洞 + 把该漏洞写进 ignore」必须被审出来

## D. 发版 / 预发 / ZAP（PR 之外的路径）

- [ ] **标签保护已配** —— ✅ 实测有效：白名单内 201，白名单外的 write 协作者
      `422 user not allowed to create protected tag`；空白名单 = 谁都不能打。
      **这条是 D 节的地基，已验证可用。**

- [ ] 打 tag / 发版 workflow 仍跑 image Trivy；ZAP full-scan 失败的处理写死
- [ ] ZAP 确认**没有** `pull_request` 触发；只打预发 URL；凭据在 Secrets 不进日志
- [ ] 预发部署有审批保护；预发凭据打不到生产

> ⚠️ **`workflow_run` 在 Forgejo 上实测未触发**（三种 workflow 名字 × 两种 types，
> 17 次运行 0 个该事件）。所以「部署成功后自动扫」不能用它，改用：
> ① 作为部署 workflow 的最后一个 job（`needs:`，推荐）② 部署脚本调 dispatch API
> ③ `schedule` 兜底。详见 [../30-security-scanning/zap-dast.md](../30-security-scanning/zap-dast.md)。

## E. Runner / Secrets / Registry

- [ ] ~~默认 `permissions: contents: read`~~ → **别把它当控制项**。

  实测已证伪：`contents: read` 与 `contents: write` 两个 job 都成功用自动 token
  推出了非保护分支（[README.md](README.md) §七 之一）。这个键被解析、被忽略。
  **真正收回写权限的是保护分支**——验收要落在那里，不在 YAML 上。

- [ ] **`pull_request_target` —— ⚠️ Forgejo 实测支持，所以这个风险是活的**

  实测触发成功（事件分布里有 2 次 `pull_request_target`）。
  它 + 自托管 runner + checkout PR 分支 = 把密钥和 runner 交给 PR 作者。
  **全库搜一遍 `pull_request_target`。**

- [ ] Fork PR 拿不到仓库 Secrets；内部仓即使永不公开，runner 仍按不可信 PR 处理
- [ ] 自托管 runner 不和生产集群混；构建不默认 `--privileged`；
      PR 工作流写的 cache 不能污染主分支 job
- [ ] Package Registry：谁能推、能否覆盖已有 tag、删包要谁批
- [ ] Artifact 谁能下、保留期、含漏洞细节的不当公开 issue

## F. 失败演练（「红了怎么办」）

- [ ] 人为放一个密钥 / 一条 Semgrep 命中 / 一个 CRITICAL CVE，确认 PR 合不了

  > 这就是 canary 仓库的作用，见 [../00-principles.md](../00-principles.md) 第 1 条。
  > 本仓库的做法：一个**故意永远红**的样本仓库，它变绿就说明扫描器坏了。

- [ ] 扫描器镜像或 action digest 404：门禁红，不是跳过
- [ ] 预发挂了或 ZAP 超时：有人接手，不是 CI 自己当过
- [ ] 忽略到期日当天：再扫必须红

---

## 最可能被绕过的五个口子（按实测重排）

| # | 口子 | Forgejo 实测 |
|---|---|---|
| 1 | **管理员 / Owner 强合** | ⚠️ **确认可绕过**，且 `apply_to_admins` 挡不住；还能直接删规则 |
| 2 | **同一 PR 改 ignore / allowlist** | 未测（Forgejo 无原生校验，必须自己在 CI 里做） |
| 3 | **必检「看起来有、实际没扫」** | ✅ Forgejo 是 fail closed，**名字对不上或 job 跳过都会挡住**，比预想安全；但代价是容易误锁 |
| 4 | **Tag / 发版 / 推包不走 PR 门禁** | ✅ 标签保护可用且有效，配了就能挡 |
| 5 | **`pull_request_target` + 自托管 runner** | ⚠️ **确认支持**，风险成立 |

**排序变化**：第 3 条在 Forgejo 上比在 GitHub 上安全（fail closed），
但第 1 和第 5 条确认成立。**优先处理 1 和 5。**

---

## 尚未验证的项（不要当成结论）

| 项 | 状态 |
|---|---|
| Renovate automerge 能否限定范围 | 未测 |
| 同一 PR 改 ignore 的检出手段 | Forgejo 无原生能力，需自建 CI 校验 |
| Package Registry 的覆盖/删除权限模型 | 未测 |
