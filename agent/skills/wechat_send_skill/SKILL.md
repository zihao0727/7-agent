# 微信按姓名发消息 Skill

## 概述

根据接收人**姓名**调用网关接口，向对方发送微信消息（纯文本、链接，或两者同时）。需在对话中准确提供姓名；`message` 与 `url` **至少填一项**。

---

## 工具：`wechat_send_by_name`

**描述**：按姓名查找联系人并发送微信消息。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 接收人姓名 |
| `message` | string | 否 | 消息正文 |
| `url` | string | 否 | 链接地址 |

**约束**：`message` 与 `url` 至少填写一项。

**请求**：`POST https://zzh.wygzc.cn/app14/v2/api/send_message_by_name`  
**Body 示例**：

```json
{
  "name": "张三",
  "message": "这是一条测试消息",
  "url": "https://example.com"
}
```

**成功响应**（工具会整理为可读文本）：

```json
{
  "success": true,
  "message": "消息已成功发送给 张三",
  "name": "张三",
  "wcid": "wxid_abc123"
}
```

**失败响应**示例：

```json
{
  "detail": "未找到用户: 张三"
}
```

---

## 使用示例

- 用户：「给张三发条微信，说会议改到下午三点」 → 调用 `wechat_send_by_name`，`name=张三`，`message=会议改到下午三点`。
- 用户：「把 https://example.com 发给李四」 → `name=李四`，`url=https://example.com`（如需可同时带简短 `message`）。

---

## 错误处理

| 情况 | 说明 |
|------|------|
| 姓名为空 | 工具返回错误，需补充姓名 |
| 未提供 message 与 url | 工具返回错误，需至少一项 |
| `detail` / HTTP 4xx/5xx | 将错误信息返回用户（如未找到用户） |
| 网络异常 | 提示网络错误 |
