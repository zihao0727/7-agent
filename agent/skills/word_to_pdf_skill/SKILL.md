# Word 转 PDF Skill

## 概述

将用户提供的**本地** Word 文件（`.doc` / `.docx`）通过远程接口 `POST /convert-word-to-pdf` 转为 PDF，并上传至对象存储。工具返回包含 `presigned_url` 的 JSON；**前端会在 AI 回复中内嵌预览 PDF，并提供下载**。

---

## 工具：`convert_word_to_pdf`

**参数**

- `file_path` (string, 必填)：本地 Word 路径（建议先确认文件存在，扩展名为 `.doc` 或 `.docx`）。

**成功返回**

工具会返回一段说明文字 + **单行 JSON**（含以下字段）：

- `success`: `true`
- `message`: 说明
- `cos_key`: 对象存储键
- `presigned_url`: PDF 预签名 URL（预览与下载）
- `file_size`: 字节数

**重要：向用户回复时，请保留工具输出中的整段 JSON（含 `presigned_url`），不要改写链接，以便界面解析并显示 PDF。**

---

## 接口说明（后端实现参考）

- **URL**: `https://zzh.wygzc.cn/app6/convert-word-to-pdf`
- **方法**: `POST`
- **Content-Type**: `multipart/form-data`
- **字段**: `file` — Word 文件

成功响应示例：

```json
{
  "success": true,
  "message": "转换并上传成功",
  "cos_key": "com/test/文档.pdf",
  "presigned_url": "https://...",
  "file_size": 123456
}
```

常见错误：`detail` 字段说明原因（400 格式错误，500 转换/生成失败等）。

环境变量 `WORD_TO_PDF_API_URL` 可覆盖默认接口地址。

---

## 使用流程

1. **对话页上传（推荐）**：用户在输入框旁点击回形针，选择 `.doc` / `.docx`。后端会把文件保存到服务器并**在用户消息里附上绝对路径**；直接用该路径调用 `convert_word_to_pdf` 即可。
2. **本地路径**：用户直接给出后端可访问的 Word 文件路径时，将 `file_path` 设为该路径。
3. 调用 `convert_word_to_pdf` 后，将工具返回的说明 + JSON **原样**写进助手回复（尤其是 JSON 块），以便前端预览 PDF。

---

## 前端行为

- 解析回复中的 `presigned_url`（指向 `.pdf`）后，在对话中 **iframe 预览**，并提供 **下载** 按钮。
- 与档案 ZIP 下载控件互不干扰（ZIP 仍走原下载条）。
