# 贡献约定

## 审查

**空批准不算审完。** 平台没有这个开关（空 Approve 照样计入 `required_approvals`），
所以这条靠规范和抽查，不要指望 Forgejo 会拦。

审查至少要能回答：这个改动想解决什么、有没有测试覆盖、失败时什么表现。

## 例外（ignore 文件）

往 `.trivyignore` / `.semgrepignore` / `.gitleaks.toml` 加豁免时，**必须**写：

```
# 原因: <为什么现在修不了>
# 到期: YYYY-MM-DD
# 负责人: @someone
CVE-2026-12345
```

CI 会解析这三行，缺一行或已过期则 job 失败——**没有 CI 校验的"必须写到期日"是纯自觉**。

同一个 PR 里"引入问题 + 把该问题写进 ignore"要被审出来。
