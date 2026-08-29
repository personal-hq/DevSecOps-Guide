# 依赖更新

Renovate 的权限模型、镜像选择，以及几个会让人误以为"没生效"的配置坑。

Renovate **AGPL-3.0**——当独立 CI 机器人跑，不会传染到被扫描的代码，但这条按许可证策略要记录在案。

## 最小权限模型

非管理员账号 + 逐仓库加协作者（write）。新仓库不手动加协作者就扫不到——**这是特性不是 bug**，不要图省事把 Renovate 账号提成 admin 一次性覆盖所有仓库。

## 镜像选择

镜像**必须用 `-full` 变体**：默认镜像只有 node（实测 v24.20.0），npm/pnpm/yarn/corepack 全无；`-full` 自带 npm 11.19.0 / pnpm 10.34.5 / yarn 4.18.0 / corepack。

用错镜像的症状：PR 里出现 "Artifact update problem"，且**锁文件没有被更新**——依赖版本声明改了，`package-lock.json`/`pnpm-lock.yaml` 却停在旧的。

## `RENOVATE_GIT_URL`

实例宣告的 `ROOT_URL` 只对隧道用户有效，Renovate 默认会拿仓库元数据里的地址去 clone，容器内部网络连不通那个地址。和 CI 里 `actions/checkout` 解析不到 forgejo 服务名是同一类根因（见 [20-ci-cd/README.md](../20-ci-cd/README.md)）。

修法：显式设置 **`RENOVATE_GIT_URL=endpoint`**（就是字面值 `endpoint`，不是填 URL）。
取值含义是「用 `RENOVATE_ENDPOINT` 推导克隆地址」，而不是用仓库元数据里那个。
实测配置（2026-08-29）：`RENOVATE_ENDPOINT=http://forgejo:3000/api/v1/` + `RENOVATE_GIT_URL=endpoint`。

## `GITHUB_COM_TOKEN` 是配额问题不是权限问题

开源项目的 changelog 是公开内容，不需要登录就能读。卡住的原因是 GitHub API 对未认证 IP 限流 60 次/小时（认证后 5000 次/小时）。日志原文是 `Rate limit exceeded`，**不是** 403。所以这个 token **不需要任何 scope**，一个空权限的账号 token 就够。

Renovate 会去 GitHub，是因为**被更新依赖的源码托管在那儿**，要去取 release notes。`fetchChangeLogs` 默认值是 `"pr"`；设成 `off` 可以完全不访问 GitHub。

## 关闭 PR = 永久忽略

Renovate 把关闭 PR 理解成"用户拒绝了这次更新"，之后不会再提这个版本。调试时如果误关了，用 `RENOVATE_RECREATE_WHEN=always` 单次重建——**不要写进常规配置**，写进去会把用户故意关掉的 PR 反复重新打开。

## 判断"修好了"要看文件列表

**不能凭"错误消失"就说修好，要看 PR 的文件列表里有没有锁文件**（见 [00-principles.md](../00-principles.md) 第二条）——Renovate 对已存在的分支不会自动重算 artifact，报错消失可能只是"这次没有新活可干"，不代表锁文件被正确更新了。
