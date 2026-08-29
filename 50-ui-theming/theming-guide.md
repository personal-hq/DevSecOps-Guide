# 怎么给自建服务做主题

## 一、先找到机制，别急着写 CSS

动手前必须回答三个问题，答错任何一个都会白干：

**1. 自定义资源放哪？**
Forgejo 是 `$FORGEJO_CUSTOM/public/assets/`，容器里是 `/data/gitea/public/assets/`。
放进去的文件按 `/assets/<相对路径>` 对外服务。

**2. 主题怎么被选中？**
```ini
[ui]
THEMES = acme            # 可选主题列表
DEFAULT_THEME = acme     # 默认
```
文件名必须是 `theme-<名字>.css`，放在 `custom/public/assets/css/`。

**3. 它是叠加还是替换？** ← **最容易搞错的一条**

Forgejo 是**替换**：选中 `acme` 之后就**不再加载**它自己的 `theme-forgejo-light.css`。
所以原主题定义过、你没重新定义的变量**全部变成未定义**，而 CSS 里
一个无法解析的 `var()` 会让**整条声明作废**（不是回退到默认值）。

症状极具误导性：某个边框/底色凭空消失，但你根本没碰过那个组件。
详见 [pitfalls.md](pitfalls.md#1) 和下面的变量审计。

## 二、优先改变量，其次才是选择器

Forgejo 的主题文件定义 272 个 CSS 变量，其中**有底层色阶**（`--zinc-*` 18 个、
`--steel-*` 17 个），47 个语义变量从 `--zinc-*` 派生。

**改一处底层色阶 = 47 个变量一致地跟着变**，比逐个覆盖语义变量省事得多，
也不会出现"改了一半、深浅不一致"的情况。

优先级：

1. **底层色阶**（`--zinc-*`）—— 中性色调性一次搞定
2. **语义变量整族**（`--color-primary` 及其 dark-1..7 / light-1..7 / alpha-10..90）
3. **官方留的钩子** —— 例如 `--fonts-override`：
   `--fonts-regular: var(--fonts-override, var(--fonts-proportional))`
   设 `--fonts-override` 就能换字体，不用跟任何规则打架
4. **才轮到写选择器** —— 且必须先做 [css-debugging.md](css-debugging.md) 的判定

## 三、变量审计（每次加删变量都要重跑）

因为是替换而非叠加，必须确认没有遗漏。方法：

```bash
# 1) 取上游原主题（换成你的版本号）
curl -sSL -o theme-upstream.css \
  https://code.forgejo.org/forgejo/forgejo/raw/tag/v16.0.3/web_src/css/themes/theme-forgejo-light.css
curl -sSL -o base.css \
  https://code.forgejo.org/forgejo/forgejo/raw/tag/v16.0.3/web_src/css/base.css
# 2) 取实例正在服务的编译产物
curl -sS -o index.css http://<实例>/assets/css/index.css
# 3) 跑审计
python3 ../tools/audit-css-vars.py theme-upstream.css theme-acme.css index.css
```

脚本在 [`../tools/audit-css-vars.py`](../tools/audit-css-vars.py)。它输出三个数：
**缺失** / **其中被裸引用会真的断** / **无人引用因而无害**。

只有第二个数需要处理。首次审计的结果是 58 缺失、24 会断——包括开关控件底槽、
按钮底色、全站输入光标、图片 diff 棋盘格、以及一整套 Fomantic 命名色。

> ⚠️ 写审计脚本时注意：正则**不能限行首**。压缩风格的 CSS 一行里有多个变量定义，
> 只匹配行首会漏掉绝大部分，得出一个假的"缺 157 个"。我第一版就是这么错的。

## 四、图标：复用，别自绘

Forgejo 内置 GitHub 的 **Octicons**（MIT），每个图标单独可取：
`/assets/img/svg/octicon-<name>.svg`。

直接拿来当 `mask-image`，好处有三：零新依赖、跟产品其余部分天然一致、
跟用户参照的 GitHub 界面是同一套图形语言。

```css
a.item::before {
  content: ""; width: 16px; height: 16px;
  background: currentColor;              /* 关键：图标继承文字颜色 */
  mask: url("data:image/svg+xml,...") no-repeat center / 16px;
}
```

**用 `mask` 而非 `background-image`**：图标自动继承 `currentColor`，
当前项变强调色时图标跟着变，不用维护两套配色。

**必须内联成 data URI**，不要引 `/assets/...`：`mask-image` 受跨源限制
（实测 `file://` 页面引 `http://` 的 SVG 遮罩为空白），内联同时省掉每图一轮请求。

自绘的代价：我先画了一版 29 个图标，做成三尺寸（16/30/64px）对照表一看——
"分支线"在 30px 下糊成一个小写 b，"提交图"和"合并箭头"在 16px 下糊成一团。
对照表见 `../artifacts/shots/logo候选对照.png`，那是**看图选型**而不是凭感觉的示范。

## 五、按 href 挂载，不要按位置

菜单项加图标时，用属性选择器而不是 `:nth-child`：

```css
a.item[href="/admin/users"]::before      { mask-image: url(...) }
a.item[href$="/settings/branches"]::before { mask-image: url(...) }   /* 后缀匹配 */
```

上游增删菜单项时不会错位。对于**没有 href 的折叠分组**，用 `:has()` 按内容识别：

```css
details.toggleable-item:has(a[href="/admin/auths"]) > summary::before { ... }
```

## 六、验证：必须看图，不能读 HTML 猜

搭一条无头浏览器管线，改一处看一处。见
[`../tools/screenshot-pipeline/`](../tools/screenshot-pipeline/)。

**判断"是我的问题还是上游的问题"有个决定性实验**：把自己的样式表从页面里摘掉，
剩下的就是上游原生行为。

```bash
curl -sS <页面> | sed -E 's#<link[^>]*theme-<你的>\.css[^>]*>##' > /tmp/upstream.html
```

我用这招确认了"个人主页搜索框裂成两截"是**我们的 bug 而不是 Forgejo 的**——
对照组渲染完全正常。省掉了一次毫无意义的上游 issue。
