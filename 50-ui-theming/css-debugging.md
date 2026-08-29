# CSS 规则不生效时怎么定位

这篇是 [00-principles.md 第 3 条](../00-principles.md#3-判断被覆盖要量不要猜)的展开：
那条铁律说的是"要量、不要猜"，这篇给出具体量的步骤和工具。

## 第一步：分清"没匹配"还是"特异度输了"

这两种情况**修法完全不同**，混淆了就会在错误的方向上反复试错（连续猜错三次
就是这么来的）。判据是这一行：

```js
document.querySelectorAll('<你的选择器>').length
```

| 结果 | 说明 | 下一步 |
|---|---|---|
| `0` | 选择器**根本没命中**任何元素 | 类名/结构假设错了，去看真实 DOM，改选择器 |
| `>0` | 命中了，但样式没生效 | 特异度问题，往下用 `getComputedStyle` 找赢家 |

先跑这一行，再决定往哪个方向查——这是唯一能省掉"猜"的步骤。

## 第二步：看实际生效值

```js
getComputedStyle(el).<属性>
```

这是浏览器**实际使用**的值，不是你以为规则应该产出的值。配合浏览器
devtools 的 Computed 面板能看到"谁赢了"，但当你需要**批量核对多个元素**、
或者要在**无头环境**里跑这个检查时，devtools 不够用，需要下面这个技术。

## 注入探针：批量核对，还能在无头环境里跑

思路：把页面存成本地静态 HTML，往里注入一段 JS，用 `getComputedStyle` 把
目标元素**及其整条父链**的关键属性写回 DOM 里，再用
`chromium --headless --dump-dom` 把渲染后的 DOM 取回来解析。这样"人肉去
devtools 里一层层点父元素"变成了一条能重复跑、能存证据的命令。

**探针脚本**（改 `TARGET_SELECTOR` 和 `PROPS` 就能用在别的元素上）：

```js
// probe.js
// 包一层 DOMContentLoaded：脚本插在 </head> 前执行时 document.body 还是 null，
// 直接 appendChild 会静默抛错、探针元素不出现——这是实测踩到的一个坑，
// 不包这层看起来"什么都没发生"，容易误以为是没找对元素。
document.addEventListener('DOMContentLoaded', function () {
  var TARGET_SELECTOR = '#inner';              // 改成你要查的元素
  var PROPS = ['display', 'color', 'border'];  // 改成你关心的属性

  var el = document.querySelector(TARGET_SELECTOR);
  var chain = [];
  while (el) {
    var cs = getComputedStyle(el);
    var row = {
      tag: el.tagName.toLowerCase(),
      id: el.id || null,
      class: el.className || null,
    };
    PROPS.forEach(function (p) { row[p] = cs.getPropertyValue(p); });
    chain.push(row);
    el = el.parentElement;
  }

  var pre = document.createElement('pre');
  pre.id = '__probe_output__';
  pre.textContent = JSON.stringify(chain, null, 2);
  document.body.appendChild(pre);
});
```

**注入 + 取回**（`PAGE` 是已经存到本地的页面 HTML）：

```bash
PAGE=/tmp/page.html
python3 - <<'PY'
probe = open('probe.js', encoding='utf-8').read()
page = open('/tmp/page.html', encoding='utf-8').read()
open('/tmp/page.injected.html', 'w', encoding='utf-8').write(
    page.replace('</head>', '<script>\n' + probe + '\n</script>\n</head>')
)
PY

timeout 30 chromium --headless --disable-gpu --no-sandbox --dump-dom \
  "file:///tmp/page.injected.html" > /tmp/dump.html

python3 - <<'PY'
import re
html = open('/tmp/dump.html', encoding='utf-8').read()
m = re.search(r'<pre id="__probe_output__">(.*?)</pre>', html, re.S)
print(m.group(1) if m else "探针没有输出——先查 TARGET_SELECTOR 是不是命中了元素")
PY
```

输出是一条从目标元素到 `<html>` 的数组，每一层带 `tag`/`id`/`class` 和你要
的属性值——父链上谁把 `display` 改成了别的值、谁的 `color` 意外被继承，
一眼能看到，不用在 devtools 里点十几次"选中父元素"。

## 量盒子：不要靠"看起来"

`getComputedStyle` 告诉你属性的值，但不会告诉你**实际占了多大、在哪**——
这个只能靠：

```js
el.getBoundingClientRect()   // { x, y, width, height, top, right, bottom, left }
```

真实案例（就是 [pitfalls.md #4](pitfalls.md#4-page-contentuser-作用域泄漏)
那次个人主页搜索框问题）：肉眼看上去像"输入框左边凭空多出一个空盒子"，
量出来的实际情况是——

```
input  width = 24    (被挤压)
button width = 387   (被撑到 100%，甚至溢出了容器)
```

跟直觉完全相反：不是输入框左边多了什么，是**按钮被撑大、把输入框挤扁了**。
先量后修，省掉了在错误方向上改代码的时间。

## 决定性实验：摘掉自己的样式表

怀疑某个渲染问题是自己的 CSS 引入的、还是 Forgejo 本来就这样，最快的验证不
是读代码猜，是**直接把自己的样式表从页面里去掉**，看剩下的上游原生行为是
什么样：

```bash
curl -sS <页面 URL> | \
  sed -E 's#<link[^>]*theme-<你的>\.css[^>]*>##' > /tmp/upstream.html
```

用 `chromium --headless --screenshot` 截一下 `/tmp/upstream.html`，跟带自己
样式表的版本对照。这招在个人主页搜索框那次直接确认了问题是自己引入的
（对照组渲染正常），省掉了一次毫无意义的上游 issue。

## `!important` 什么时候正当，什么时候是偷懒

**正当**：已经用第一步确认选择器命中了（`querySelectorAll` 返回 `>0`），
也用 `getComputedStyle` 找到了赢的那条规则，量过它的特异度确实比你的高。

**偷懒**：还没做上面这些，遇到"不生效"就先加 `!important` 试试。这种做法
即使侥幸压过了当前这条规则，下次上游改了 CSS 顺序或换了更高特异度的规则，
问题会以更难查的方式回来。

真实例子（[00-principles.md #3](../00-principles.md#3-判断被覆盖要量不要猜)
的原始案例）：外链隐藏规则一开始不生效，`querySelectorAll` 返回 `1`——
选择器是对的，输在特异度。目标元素的父链上有 `nav#navbar`，上游用 **ID
选择器**（特异度 `(1,0,0)`）给它设了 `display:flex`，压过本规则的
`(0,2,2)`。ID 在特异度比较里排第一位，`(0,2,2)` 无论类和类型选择器堆多少
都不可能追上 `(1,0,0)`——这种情况下 `!important` 是唯一可行的手段，不是
图省事。
