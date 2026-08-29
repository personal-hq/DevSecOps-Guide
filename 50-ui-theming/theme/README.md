# 主题成品

**这是参考产物的快照，不是部署源。** 真实部署在 Forgejo 实例自己的
`custom/` 目录里；这份拷贝是留着给别的项目参考、或者重新安装时对照用的。

## 文件清单

| 文件 | 用途 |
|---|---|
| `theme-acme.css` | 主题本体：变量覆盖 + 选择器覆盖，见 [../theming-guide.md](../theming-guide.md) |
| `assets/logo.svg` | 顶栏 / 登录页 logo |
| `assets/favicon.svg` | 浏览器标签图标 |
| `assets/InterVariable.woff2` | 正文字体，可变字重 |

## 安装位置

对应容器内 `/data/gitea/public/assets/` 下的三个子目录，属主 `3000:3000`
（本实例的运行 UID，装的时候要对齐，不然 Forgejo 进程读不了）：

| 源文件 | 容器内目标路径 |
|---|---|
| `theme-acme.css` | `/data/gitea/public/assets/css/theme-acme.css` |
| `assets/logo.svg` | `/data/gitea/public/assets/img/logo.svg` |
| `assets/favicon.svg` | `/data/gitea/public/assets/img/favicon.svg` |
| `assets/InterVariable.woff2` | `/data/gitea/public/assets/fonts/InterVariable.woff2` |

主题文件名必须是 `theme-<名字>.css` 这个格式——文件名本身就是主题标识，
`THEMES` 配置项里写的名字要和它对上。

**改 CSS 不需要重启**，容器直接从挂载目录里读，保存即生效（还要留意
[pitfalls.md #10](../pitfalls.md#10-静态资源缓存-6h-且-url-不带内容哈希)
的缓存问题）。**改 `app.ini` 需要重启**才能生效。

## 需要的配置

`app.ini` 里：

```ini
[ui]
THEMES = acme
DEFAULT_THEME = acme
```

**改完 `DEFAULT_THEME` 别忘了这一步**——它只对新账号生效，已有账号的主题在
创建时就写死进了数据库，必须手动改：

```bash
docker compose exec -T db psql -U forgejo -d forgejo \
  -c "UPDATE \"user\" SET theme='acme';"
```

原因见 [pitfalls.md #9](../pitfalls.md#9-default_theme-不覆盖已有账号)。

## 字体来源

`InterVariable.woff2` 来自 [`@fontsource-variable/inter`](https://www.npmjs.com/package/@fontsource-variable/inter)
的拉丁子集可变字重版本，约 48KB。协议 **SIL OFL**，允许嵌入产品并自建
`@font-face`。

## 图标来源

`logo.svg` / `favicon.svg` 是本项目画的，风格上跟正文里用的图标集
一致——正文（侧栏、按钮）用的图标不是自绘的，是 Forgejo 自带的
**Octicons**（MIT，和 GitHub 同一套），按需从
`/assets/img/svg/octicon-<name>.svg` 取，内联成 data URI 用在 `mask-image`
上。取用方式和理由见 [theming-guide.md 第四节](../theming-guide.md#四图标复用别自绘)。
