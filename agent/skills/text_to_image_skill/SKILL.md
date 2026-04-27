---
description: "文生图：根据提示词异步生成图片，工具内自动轮询任务直至成功或失败"
---

# 文生图 Skill（Text to Image）

用户描述画面需求时，使用工具 **`text_to_image`**：根据提示词调用服务端文生图接口，**创建任务并在服务端轮询状态**，直到返回图片 URL、明确失败或超时。

## 工具：`text_to_image`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | string | 是 | 提示词，不能为空 |
| `width` | integer | 否 | 宽，默认 1024 |
| `height` | integer | 否 | 高，默认 1024 |
| `instance_type` | string | 否 | 实例类型，默认 `default` |
| `use_personal_queue` | boolean | 否 | 是否个人队列，默认 false |
| `max_wait_seconds` | integer | 否 | 最长等待秒数，默认 600 |
| `poll_interval_seconds` | number | 否 | 轮询间隔秒，默认 2 |

鉴权由服务端完成（`RUNNINGHUB_API_KEY` / `API_KEY`），**调用方不要在参数里传 Key**。

## 行为说明

1. **创建任务**：`POST https://zzh.wygzc.cn/app10/api/text-to-image`，JSON 体字段与网关一致（`prompt`、`width`、`height`、`instanceType`、`usePersonalQueue` 等）。
2. **轮询状态**：`POST https://zzh.wygzc.cn/app10/api/v2/query`，body 为 `{"taskId": "..."}`，直到 `status` 为 `SUCCESS`（解析 `results` 中的 `url`）或 `FAILED`，或超出 `max_wait_seconds`。
3. **面向用户**：用简短中文说明是否成功，给出**可点击的图片链接**；不要整段粘贴原始 JSON。

## 示例

用户：「画一张水彩风格的猫」

```text
text_to_image(
  prompt="一只猫，水彩风格",
  width=1024,
  height=1024,
  _purpose="按用户要求生成水彩风格猫咪插图"
)
```

## 错误与降级

- HTTP 4xx/5xx：响应体可能为 `{"detail": "..."}`，将 `detail` 含义转告用户。
- 超时：告知用户最后已知状态，可建议缩小尺寸、简化提示词或稍后重试。
- 需本能力时，请用户在界面中**启用 `text_to_image` 所在技能**；未启用时无法调用该工具。
