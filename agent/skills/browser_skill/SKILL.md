# Browser Skill — 浏览器自动化

你现在拥有一套完整的浏览器自动化工具，可以像人类一样操控浏览器抓取网页信息。

## 工具速查

| 工具 | 功能 | 常用场景 |
|------|------|---------|
| `browser_navigate` | 导航到 URL | 打开目标网页，**每次新任务必须先调用** |
| `browser_screenshot` | 截图 | 查看当前页面状态 |
| `browser_extract_text` | 提取文本 | 正文、标题、价格、评论 |
| `browser_extract_attrs` | 提取 HTML 属性 | 链接(href)、图片(src)、data-* |
| `browser_extract_table` | 解析表格 | 数据表 → JSON/CSV |
| `browser_scroll` | 滚动页面 | 触发无限滚动加载更多内容 |
| `browser_click` | 点击元素 | 翻页、展开、跳转 |
| `browser_extract_list` | 批量列表抓取 | 电商商品、搜索结果、新闻列表 |

---

## 使用流程

### 基础抓取
```
1. browser_navigate(url)          → 打开页面
2. browser_extract_text()         → 提取正文（或用选择器精准定位）
3. browser_screenshot()           → 截图确认
```

### 抓取商品列表（分页）
```
1. browser_navigate(url)
2. browser_extract_list(
     item_selector=".product-item",
     fields={"name": ".title", "price": ".price", "link": "a"},
     max_pages=5,
     next_button_selector="a.next"
   )
```

### 无限滚动内容（如社交媒体）
```
1. browser_navigate(url)
2. browser_extract_list(
     item_selector=".post",
     fields={"content": ".text", "author": ".username"},
     infinite_scroll=True,
     scroll_rounds=10
   )
```

### 抓取表格数据
```
1. browser_navigate(url)
2. browser_extract_table(output_format="csv")
```

### 抓取所有链接
```
1. browser_navigate(url)
2. browser_extract_attrs(selector="a", attrs=["href", "title"])
```

---

## 注意事项

- **必须先导航**：所有工具（除 `browser_navigate`）都需要先执行 `browser_navigate`
- **截图验证**：复杂任务建议每步截图，通过 `screenshot_url` 确认页面状态
- **选择器优先**：提取特定区域用 CSS 选择器，如 `.price`、`#content`、`[data-testid="price"]`
- **等待时机**：动态加载页面用 `wait_for="networkidle"`；普通页面用 `wait_for="load"`（默认）
- **反爬处理**：对于有反爬保护的网站，浏览器已配置常见的绕过设置
- **每次结果都含 `screenshot_url`**：可在右侧浏览器面板中实时查看

---

## _purpose 字段

调用工具时，在参数中加入 `_purpose` 字段（简短的中文说明），便于用户在界面上理解当前操作：
```json
{
  "url": "https://example.com",
  "_purpose": "打开目标商品页面"
}
```
