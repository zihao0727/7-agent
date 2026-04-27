# Code Runner Skill — 代码编写与运行

你已解锁 **`run_code`** 工具：在服务端沙箱中执行代码，**标准输出、错误信息与生成的 matplotlib 图表**会写入当前会话，用户可在界面**右侧「代码执行」面板**中查看（按会话隔离，其他会话不可见）。

## 工具速查

| 工具 | 功能 | 常用场景 |
|------|------|----------|
| `run_code` | 执行完整代码片段 | 数据分析、算法验证、绘图、脚本处理 |

## 必填参数

每次调用**必须**同时提供：

- **`code`**（string）：完整、可执行的源代码。
- **`description`**（string）：一句话说明本次运行目的（会显示给用户，例如「绘制 2024 年月度销售折线图」）。

可选：

- **`language`**：`python` \| `javascript` \| `typescript` \| `bash`（默认 `python`）。
- **`timeout`**：超时秒数（默认 30）。
- **`session_id`**：由系统自动注入，**不要手动填写**。

调用时请附带 **`_purpose`**（系统提示要求），简要说明为何此时执行这段代码。

## 使用示例

### Python 数据分析 + 中文图表标题

```text
run_code(
  language="python",
  description="生成示例正弦曲线图",
  code="""
import numpy as np
import matplotlib.pyplot as plt

x = np.linspace(0, 2*np.pi, 200)
y = np.sin(x)
plt.figure(figsize=(8, 4))
plt.plot(x, y)
plt.title('正弦波')
plt.xlabel('x')
plt.ylabel('sin(x)')
plt.tight_layout()
plt.show()
print('计算完成')
""",
  _purpose="用 matplotlib 绘制正弦波并展示给用户"
)
```

### JavaScript 验证逻辑

```text
run_code(
  language="javascript",
  description="验证斐波那契函数",
  code="function fib(n){ return n<=1 ? n : fib(n-1)+fib(n-2); }\\nconsole.log('fib(10)=', fib(10));",
  _purpose="运行 JS 验证算法输出"
)
```

### Bash 文件批处理

```text
run_code(
  language="bash",
  description="统计当前目录文件数量",
  code="echo \"文件数: $(ls -1 | wc -l)\"",
  _purpose="用 shell 统计目录文件数"
)
```

## 与右侧面板的关系

- 每次成功执行会在**当前会话**追加一条记录：描述、代码（可折叠）、终端输出、**图表（若有）**。
- 你在工具返回文本中看到的 stdout/stderr 摘要与用户面板内容一致；**图表以面板内预览为准**。

## 注意事项

- **禁止**发送空的 `code` 或空对象 `{}`。
- Python 下 **matplotlib 已配置中文字体与负号**，可直接使用中文标题/标签。
- 每次执行为**独立进程**，变量不会在多次 `run_code` 之间保留。
- 需要本能力时，请用户在界面中**启用「code_runner」技能**；未启用时你无法调用 `run_code`。
