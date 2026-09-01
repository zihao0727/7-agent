"use client";

export type LarkIdentity = "auto" | "bot" | "user";
export type LarkFieldType = "text" | "textarea" | "select" | "checkbox" | "number";

export interface LarkActionField {
  key: string;
  label: string;
  type?: LarkFieldType;
  placeholder?: string;
  defaultValue?: string | boolean;
  required?: boolean;
  options?: Array<{ label: string; value: string }>;
}

export interface LarkActionPreset {
  id: string;
  label: string;
  description: string;
  identity: Exclude<LarkIdentity, "auto">;
  fields: LarkActionField[];
  buildCommand: (values: Record<string, string | boolean>) => string[];
}

export interface LarkDomainPreset {
  id: string;
  label: string;
  icon: string;
  actions: LarkActionPreset[];
}

const text = (value: string | boolean | undefined): string => {
  if (typeof value !== "string") return "";
  return value.trim();
};

const flag = (
  args: string[],
  name: string,
  value: string | boolean | undefined
): void => {
  const clean = text(value);
  if (clean) args.push(name, clean);
};

const boolFlag = (
  args: string[],
  name: string,
  value: string | boolean | undefined
): void => {
  if (value === true) args.push(name);
};

const stringField = (
  key: string,
  label: string,
  placeholder = "",
  required = false
): LarkActionField => ({
  key,
  label,
  placeholder,
  required,
});

const textareaField = (
  key: string,
  label: string,
  placeholder = "",
  required = false
): LarkActionField => ({
  key,
  label,
  type: "textarea",
  placeholder,
  required,
});

const numberField = (
  key: string,
  label: string,
  defaultValue = ""
): LarkActionField => ({
  key,
  label,
  type: "number",
  defaultValue,
});

const selectField = (
  key: string,
  label: string,
  options: Array<{ label: string; value: string }>,
  defaultValue: string
): LarkActionField => ({
  key,
  label,
  type: "select",
  options,
  defaultValue,
});

const checkboxField = (
  key: string,
  label: string,
  defaultValue = false
): LarkActionField => ({
  key,
  label,
  type: "checkbox",
  defaultValue,
});

const docApi = selectField("apiVersion", "API 版本", [
  { label: "v2", value: "v2" },
  { label: "v1", value: "v1" },
], "v2");

export const LARK_DOMAINS: LarkDomainPreset[] = [
  {
    id: "docs",
    label: "云文档",
    icon: "file-text",
    actions: [
      {
        id: "docs-search",
        label: "搜索文档",
        description: "按关键词搜索云文档、知识库和表格文件。",
        identity: "user",
        fields: [
          stringField("query", "关键词", "项目计划", true),
          numberField("pageSize", "数量", "10"),
        ],
        buildCommand: (v) => {
          const args = ["docs", "+search"];
          flag(args, "--query", v.query);
          flag(args, "--page-size", v.pageSize);
          return args;
        },
      },
      {
        id: "docs-fetch",
        label: "读取文档",
        description: "按文档 URL 或 token 拉取文档内容。",
        identity: "user",
        fields: [stringField("doc", "文档 URL / token", "https://...", true), docApi],
        buildCommand: (v) => ["docs", "+fetch", "--doc", text(v.doc), "--api-version", text(v.apiVersion)],
      },
      {
        id: "docs-create",
        label: "创建文档",
        description: "用 Markdown 创建云文档，可选指定父文件夹。",
        identity: "user",
        fields: [
          stringField("title", "标题", "项目纪要", true),
          textareaField("markdown", "Markdown", "# 标题\n\n内容", true),
          stringField("folderToken", "文件夹 token", "可空"),
          docApi,
        ],
        buildCommand: (v) => {
          const args = ["docs", "+create", "--title", text(v.title), "--markdown", text(v.markdown), "--api-version", text(v.apiVersion)];
          flag(args, "--folder-token", v.folderToken);
          return args;
        },
      },
      {
        id: "docs-update",
        label: "更新文档",
        description: "追加、覆盖或替换文档内容。",
        identity: "user",
        fields: [
          stringField("doc", "文档 URL / token", "https://...", true),
          selectField("mode", "模式", [
            { label: "追加", value: "append" },
            { label: "覆盖", value: "overwrite" },
            { label: "全文替换", value: "replace_all" },
          ], "append"),
          textareaField("markdown", "Markdown", "新增内容", true),
          stringField("newTitle", "新标题", "可空"),
          docApi,
        ],
        buildCommand: (v) => {
          const args = ["docs", "+update", "--doc", text(v.doc), "--mode", text(v.mode), "--markdown", text(v.markdown), "--api-version", text(v.apiVersion)];
          flag(args, "--new-title", v.newTitle);
          return args;
        },
      },
    ],
  },
  {
    id: "drive",
    label: "云空间",
    icon: "folder",
    actions: [
      {
        id: "drive-upload",
        label: "上传文件",
        description: "把本地文件上传到云空间或指定文件夹。",
        identity: "user",
        fields: [
          stringField("file", "本地路径", "D:\\\\path\\\\file.docx", true),
          stringField("folderToken", "文件夹 token", "可空"),
          stringField("name", "显示名称", "可空"),
        ],
        buildCommand: (v) => {
          const args = ["drive", "+upload", "--file", text(v.file)];
          flag(args, "--folder-token", v.folderToken);
          flag(args, "--name", v.name);
          return args;
        },
      },
      {
        id: "drive-download",
        label: "下载文件",
        description: "按 file token 下载云空间文件到本地路径。",
        identity: "user",
        fields: [
          stringField("fileToken", "File token", "", true),
          stringField("output", "保存路径", "D:\\\\Downloads\\\\file.bin", true),
          checkboxField("overwrite", "覆盖已有文件"),
        ],
        buildCommand: (v) => {
          const args = ["drive", "+download", "--file-token", text(v.fileToken), "--output", text(v.output)];
          boolFlag(args, "--overwrite", v.overwrite);
          return args;
        },
      },
      {
        id: "drive-export",
        label: "导出文件",
        description: "把文档、表格或多维表格导出到本地目录。",
        identity: "user",
        fields: [
          stringField("token", "文档 token", "", true),
          selectField("docType", "类型", [
            { label: "文档 docx", value: "docx" },
            { label: "旧文档 doc", value: "doc" },
            { label: "表格 sheet", value: "sheet" },
            { label: "多维表格 bitable", value: "bitable" },
          ], "docx"),
          selectField("extension", "导出格式", [
            { label: "PDF", value: "pdf" },
            { label: "DOCX", value: "docx" },
            { label: "XLSX", value: "xlsx" },
            { label: "CSV", value: "csv" },
            { label: "Markdown", value: "markdown" },
          ], "pdf"),
          stringField("outputDir", "输出目录", "D:\\\\Downloads"),
          checkboxField("overwrite", "覆盖已有文件"),
        ],
        buildCommand: (v) => {
          const args = ["drive", "+export", "--token", text(v.token), "--doc-type", text(v.docType), "--file-extension", text(v.extension)];
          flag(args, "--output-dir", v.outputDir);
          boolFlag(args, "--overwrite", v.overwrite);
          return args;
        },
      },
      {
        id: "drive-folder",
        label: "创建文件夹",
        description: "在云空间根目录或指定文件夹下创建文件夹。",
        identity: "user",
        fields: [
          stringField("name", "文件夹名", "项目资料", true),
          stringField("folderToken", "父文件夹 token", "可空"),
        ],
        buildCommand: (v) => {
          const args = ["drive", "+create-folder", "--name", text(v.name)];
          flag(args, "--folder-token", v.folderToken);
          return args;
        },
      },
    ],
  },
  {
    id: "sheets",
    label: "表格",
    icon: "table",
    actions: [
      {
        id: "sheets-create",
        label: "创建表格",
        description: "创建电子表格，并可写入表头和初始数据。",
        identity: "user",
        fields: [
          stringField("title", "标题", "数据表", true),
          textareaField("headers", "表头 JSON", "[\"姓名\",\"状态\"]"),
          textareaField("data", "数据 JSON", "[[\"Alice\",\"进行中\"]]"),
          stringField("folderToken", "文件夹 token", "可空"),
        ],
        buildCommand: (v) => {
          const args = ["sheets", "+create", "--title", text(v.title)];
          flag(args, "--headers", v.headers);
          flag(args, "--data", v.data);
          flag(args, "--folder-token", v.folderToken);
          return args;
        },
      },
      {
        id: "sheets-read",
        label: "读取单元格",
        description: "读取指定表格范围。",
        identity: "user",
        fields: [
          stringField("token", "Spreadsheet token", "", true),
          stringField("range", "范围", "A1:D20", true),
          stringField("sheetId", "Sheet ID", "可空"),
        ],
        buildCommand: (v) => {
          const args = ["sheets", "+read", "--spreadsheet-token", text(v.token), "--range", text(v.range)];
          flag(args, "--sheet-id", v.sheetId);
          return args;
        },
      },
      {
        id: "sheets-write",
        label: "写入单元格",
        description: "覆盖写入指定范围。",
        identity: "user",
        fields: [
          stringField("token", "Spreadsheet token", "", true),
          stringField("range", "范围", "A1:B2", true),
          textareaField("values", "二维数组 JSON", "[[\"姓名\",\"状态\"],[\"Alice\",\"完成\"]]", true),
          stringField("sheetId", "Sheet ID", "可空"),
        ],
        buildCommand: (v) => {
          const args = ["sheets", "+write", "--spreadsheet-token", text(v.token), "--range", text(v.range), "--values", text(v.values)];
          flag(args, "--sheet-id", v.sheetId);
          return args;
        },
      },
      {
        id: "sheets-append",
        label: "追加行",
        description: "在表格末尾追加二维数组数据。",
        identity: "user",
        fields: [
          stringField("token", "Spreadsheet token", "", true),
          stringField("range", "范围", "A:B", true),
          textareaField("values", "二维数组 JSON", "[[\"Bob\",\"待办\"]]", true),
          stringField("sheetId", "Sheet ID", "可空"),
        ],
        buildCommand: (v) => {
          const args = ["sheets", "+append", "--spreadsheet-token", text(v.token), "--range", text(v.range), "--values", text(v.values)];
          flag(args, "--sheet-id", v.sheetId);
          return args;
        },
      },
      {
        id: "sheets-find",
        label: "查找单元格",
        description: "在表格中搜索文本。",
        identity: "user",
        fields: [
          stringField("token", "Spreadsheet token", "", true),
          stringField("find", "查找内容", "Alice", true),
          stringField("range", "范围", "可空"),
          checkboxField("ignoreCase", "忽略大小写", true),
        ],
        buildCommand: (v) => {
          const args = ["sheets", "+find", "--spreadsheet-token", text(v.token), "--find", text(v.find)];
          flag(args, "--range", v.range);
          boolFlag(args, "--ignore-case", v.ignoreCase);
          return args;
        },
      },
    ],
  },
  {
    id: "base",
    label: "多维表格",
    icon: "database",
    actions: [
      {
        id: "base-table-list",
        label: "表列表",
        description: "列出一个 Base 下的所有表。",
        identity: "user",
        fields: [stringField("baseToken", "Base token", "", true)],
        buildCommand: (v) => ["base", "+table-list", "--base-token", text(v.baseToken)],
      },
      {
        id: "base-field-list",
        label: "字段列表",
        description: "列出表字段。",
        identity: "user",
        fields: [
          stringField("baseToken", "Base token", "", true),
          stringField("tableId", "Table ID / 名称", "", true),
        ],
        buildCommand: (v) => ["base", "+field-list", "--base-token", text(v.baseToken), "--table-id", text(v.tableId)],
      },
      {
        id: "base-record-list",
        label: "记录列表",
        description: "读取表记录，可选指定视图和数量。",
        identity: "user",
        fields: [
          stringField("baseToken", "Base token", "", true),
          stringField("tableId", "Table ID / 名称", "", true),
          stringField("viewId", "View ID", "可空"),
          numberField("limit", "数量", "50"),
        ],
        buildCommand: (v) => {
          const args = ["base", "+record-list", "--base-token", text(v.baseToken), "--table-id", text(v.tableId)];
          flag(args, "--view-id", v.viewId);
          flag(args, "--limit", v.limit);
          return args;
        },
      },
      {
        id: "base-record-search",
        label: "搜索记录",
        description: "用 Base JSON DSL 搜索记录。",
        identity: "user",
        fields: [
          stringField("baseToken", "Base token", "", true),
          stringField("tableId", "Table ID / 名称", "", true),
          textareaField("json", "搜索 JSON", "{\"keyword\":\"Alice\",\"search_fields\":[\"Name\"]}", true),
        ],
        buildCommand: (v) => ["base", "+record-search", "--base-token", text(v.baseToken), "--table-id", text(v.tableId), "--json", text(v.json)],
      },
      {
        id: "base-record-upsert",
        label: "新增/更新记录",
        description: "按字段名或字段 ID 写入一条记录。",
        identity: "user",
        fields: [
          stringField("baseToken", "Base token", "", true),
          stringField("tableId", "Table ID / 名称", "", true),
          stringField("recordId", "Record ID", "更新时填写，可空"),
          textareaField("json", "记录 JSON", "{\"Name\":\"Alice\"}", true),
        ],
        buildCommand: (v) => {
          const args = ["base", "+record-upsert", "--base-token", text(v.baseToken), "--table-id", text(v.tableId), "--json", text(v.json)];
          flag(args, "--record-id", v.recordId);
          return args;
        },
      },
    ],
  },
  {
    id: "mail",
    label: "邮件",
    icon: "mail",
    actions: [
      {
        id: "mail-triage",
        label: "搜索邮件",
        description: "列出或搜索邮件摘要。",
        identity: "user",
        fields: [
          stringField("query", "关键词", "budget"),
          stringField("mailbox", "邮箱", "me"),
          numberField("max", "数量", "20"),
        ],
        buildCommand: (v) => {
          const args = ["mail", "+triage", "--format", "json"];
          flag(args, "--query", v.query);
          flag(args, "--mailbox", v.mailbox);
          flag(args, "--max", v.max);
          return args;
        },
      },
      {
        id: "mail-message",
        label: "读取邮件",
        description: "按 message_id 读取邮件正文和附件信息。",
        identity: "user",
        fields: [
          stringField("messageId", "Message ID", "", true),
          stringField("mailbox", "邮箱", "me"),
        ],
        buildCommand: (v) => {
          const args = ["mail", "+message", "--message-id", text(v.messageId)];
          flag(args, "--mailbox", v.mailbox);
          return args;
        },
      },
      {
        id: "mail-thread",
        label: "读取会话",
        description: "按 thread_id 读取完整邮件会话。",
        identity: "user",
        fields: [
          stringField("threadId", "Thread ID", "", true),
          stringField("mailbox", "邮箱", "me"),
        ],
        buildCommand: (v) => {
          const args = ["mail", "+thread", "--thread-id", text(v.threadId)];
          flag(args, "--mailbox", v.mailbox);
          return args;
        },
      },
      {
        id: "mail-draft",
        label: "写邮件草稿",
        description: "创建邮件草稿，默认不会立即发送。",
        identity: "user",
        fields: [
          stringField("to", "收件人", "alice@example.com", true),
          stringField("subject", "主题", "项目更新", true),
          textareaField("body", "正文", "你好，...", true),
          stringField("cc", "抄送", "可空"),
        ],
        buildCommand: (v) => {
          const args = ["mail", "+send", "--to", text(v.to), "--subject", text(v.subject), "--body", text(v.body)];
          flag(args, "--cc", v.cc);
          return args;
        },
      },
    ],
  },
  {
    id: "task",
    label: "任务",
    icon: "check-square",
    actions: [
      {
        id: "task-my",
        label: "我的任务",
        description: "查看分配给当前用户的任务。",
        identity: "user",
        fields: [
          stringField("query", "关键词", "可空"),
          numberField("pageLimit", "数量", "20"),
        ],
        buildCommand: (v) => {
          const args = ["task", "+get-my-tasks"];
          flag(args, "--query", v.query);
          flag(args, "--page-limit", v.pageLimit);
          return args;
        },
      },
      {
        id: "task-create",
        label: "创建任务",
        description: "创建一个任务，可指定负责人和截止日期。",
        identity: "user",
        fields: [
          stringField("summary", "标题", "跟进客户", true),
          textareaField("description", "描述", "任务详情"),
          stringField("assignee", "负责人 open_id", "可空"),
          stringField("due", "截止日期", "2026-05-10 或 +2d"),
        ],
        buildCommand: (v) => {
          const args = ["task", "+create", "--summary", text(v.summary)];
          flag(args, "--description", v.description);
          flag(args, "--assignee", v.assignee);
          flag(args, "--due", v.due);
          return args;
        },
      },
      {
        id: "task-search",
        label: "搜索任务",
        description: "按关键词搜索任务。",
        identity: "user",
        fields: [
          stringField("query", "关键词", "客户", true),
          numberField("pageLimit", "数量", "20"),
        ],
        buildCommand: (v) => {
          const args = ["task", "+search", "--query", text(v.query)];
          flag(args, "--page-limit", v.pageLimit);
          return args;
        },
      },
      {
        id: "task-complete",
        label: "完成任务",
        description: "把指定任务标记为完成。",
        identity: "user",
        fields: [stringField("taskId", "Task ID", "", true)],
        buildCommand: (v) => ["task", "+complete", "--task-id", text(v.taskId)],
      },
    ],
  },
  {
    id: "people",
    label: "通讯录",
    icon: "users",
    actions: [
      {
        id: "contact-search",
        label: "搜索员工",
        description: "按姓名、邮箱或手机号搜索员工。",
        identity: "user",
        fields: [
          stringField("query", "关键词", "张三", true),
          numberField("pageSize", "数量", "20"),
        ],
        buildCommand: (v) => {
          const args = ["contact", "+search-user", "--query", text(v.query)];
          flag(args, "--page-size", v.pageSize);
          return args;
        },
      },
      {
        id: "contact-get",
        label: "查看用户",
        description: "查看自己或指定用户信息。",
        identity: "user",
        fields: [
          stringField("userId", "User ID", "留空查看自己"),
          selectField("userIdType", "ID 类型", [
            { label: "open_id", value: "open_id" },
            { label: "union_id", value: "union_id" },
            { label: "user_id", value: "user_id" },
          ], "open_id"),
        ],
        buildCommand: (v) => {
          const args = ["contact", "+get-user"];
          flag(args, "--user-id", v.userId);
          flag(args, "--user-id-type", v.userIdType);
          return args;
        },
      },
    ],
  },
  {
    id: "meetings",
    label: "会议",
    icon: "video",
    actions: [
      {
        id: "minutes-search",
        label: "搜索妙记",
        description: "按关键词、时间、参与人搜索妙记。",
        identity: "user",
        fields: [
          stringField("query", "关键词", "周会"),
          stringField("start", "开始日期", "2026-05-01"),
          stringField("end", "结束日期", "2026-05-08"),
        ],
        buildCommand: (v) => {
          const args = ["minutes", "+search"];
          flag(args, "--query", v.query);
          flag(args, "--start", v.start);
          flag(args, "--end", v.end);
          return args;
        },
      },
      {
        id: "vc-search",
        label: "搜索会议记录",
        description: "按关键词或时间范围搜索视频会议记录。",
        identity: "user",
        fields: [
          stringField("query", "关键词", "复盘"),
          stringField("start", "开始日期", "2026-05-01"),
          stringField("end", "结束日期", "2026-05-08"),
        ],
        buildCommand: (v) => {
          const args = ["vc", "+search"];
          flag(args, "--query", v.query);
          flag(args, "--start", v.start);
          flag(args, "--end", v.end);
          return args;
        },
      },
      {
        id: "vc-notes",
        label: "获取会议纪要",
        description: "通过 meeting_id、minute_token 或日历事件 ID 获取纪要。",
        identity: "user",
        fields: [
          stringField("minuteTokens", "Minute tokens", "逗号分隔"),
          stringField("meetingIds", "Meeting IDs", "逗号分隔"),
          stringField("calendarEventIds", "Calendar event IDs", "逗号分隔"),
        ],
        buildCommand: (v) => {
          const args = ["vc", "+notes"];
          flag(args, "--minute-tokens", v.minuteTokens);
          flag(args, "--meeting-ids", v.meetingIds);
          flag(args, "--calendar-event-ids", v.calendarEventIds);
          return args;
        },
      },
    ],
  },
  {
    id: "wiki",
    label: "知识库",
    icon: "book-open",
    actions: [
      {
        id: "wiki-space-list",
        label: "知识空间",
        description: "列出可访问的知识空间。",
        identity: "user",
        fields: [checkboxField("pageAll", "自动分页", true)],
        buildCommand: (v) => {
          const args = ["wiki", "spaces", "list"];
          boolFlag(args, "--page-all", v.pageAll);
          return args;
        },
      },
      {
        id: "wiki-node-list",
        label: "节点列表",
        description: "列出知识空间下的子节点。",
        identity: "user",
        fields: [textareaField("params", "查询参数 JSON", "{\"space_id\":\"spc_xxx\",\"parent_node_token\":\"\"}", true)],
        buildCommand: (v) => ["wiki", "nodes", "list", "--params", text(v.params)],
      },
      {
        id: "wiki-node-create",
        label: "创建节点",
        description: "在知识库中创建文档节点。",
        identity: "user",
        fields: [
          stringField("title", "标题", "项目资料", true),
          stringField("spaceId", "Space ID", "my_library"),
          stringField("parentNodeToken", "父节点 token", "可空"),
          selectField("objType", "对象类型", [
            { label: "docx", value: "docx" },
            { label: "sheet", value: "sheet" },
            { label: "bitable", value: "bitable" },
            { label: "slides", value: "slides" },
          ], "docx"),
        ],
        buildCommand: (v) => {
          const args = ["wiki", "+node-create", "--title", text(v.title), "--obj-type", text(v.objType)];
          flag(args, "--space-id", v.spaceId);
          flag(args, "--parent-node-token", v.parentNodeToken);
          return args;
        },
      },
    ],
  },
];

export function initialActionValues(action: LarkActionPreset): Record<string, string | boolean> {
  return Object.fromEntries(
    action.fields.map((field) => [
      field.key,
      field.defaultValue ?? (field.type === "checkbox" ? false : ""),
    ])
  );
}
