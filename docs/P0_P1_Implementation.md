# P0 & P1 实现说明文档

## 概览

本次实现了 Hermes Agent 的两个核心特性：

### P0: 自动技能生成（学习闭环）
让 Agent 从经验中学习，自动生成可复用的技能文档。

### P1: 服务端完整 Agent 循环
支持长时间运行的后台任务，无需前端 maxSteps 驱动。

---

## P0: 自动技能生成 🎓

### 核心机制

```
执行复杂任务 → 检测工具调用数 → 自动分析提取 → 生成技能文档 → 用户确认 → 激活使用
```

### 实现文件

1. **`backend/skill_extractor.py`** - 核心服务
   - `analyze_task_complexity()` - 分析任务复杂度（阈值：5+ 工具调用）
   - `extract_skill_from_session()` - 使用 LLM 从对话历史提取技能
   - `confirm_auto_skill()` - 用户确认/拒绝技能
   - `get_active_skills_for_prompt()` - 获取已激活技能，注入到 prompt

2. **`backend/agent_runner.py`** - 集成点
   - `trigger_skill_extraction_if_needed()` - 在会话结束时触发提取

3. **`backend/routers/auto_skills.py`** - API 端点
   - `GET /api/auto-skills/list` - 列出自动生成的技能
   - `GET /api/auto-skills/{skill_id}` - 查看技能详情
   - `POST /api/auto-skills/{skill_id}/confirm` - 确认/拒绝技能

4. **`backend/routers/agent_loop.py`** - 服务端循环中集成
   - 任务完成后自动触发技能提取

### 使用流程

#### 1. Agent 自动学习

当用户完成一个复杂任务（5+ 工具调用）后，系统会自动：

```python
# 在 backend/agent_runner.py 或 backend/routers/agent_loop.py 中
# 任务完成时自动触发
await trigger_skill_extraction_if_needed(
    session_id=session_id,
    user_id=user_id,
    messages=conversation_messages,
)
```

#### 2. 用户查看待确认的技能

```bash
# 列出待确认的技能
GET /api/auto-skills/list?include_archived=false

# 响应示例
{
  "skills": [
    {
      "id": "uuid-1234",
      "name": "stock_price_query",
      "title": "查询股票实时价格",
      "description": "使用 akshare 工具查询 A 股实时价格",
      "trigger_patterns": ["查股价", "股票价格", "查询股票"],
      "required_tools": ["akshare_stock_quote"],
      "status": "pending",
      "confidence": 0.85,
      "created_at": "2026-07-06T10:30:00Z"
    }
  ],
  "total": 1
}
```

#### 3. 用户确认激活技能

```bash
# 激活技能
POST /api/auto-skills/{skill_id}/confirm
{
  "approved": true
}
```

#### 4. 下次自动应用

激活后，技能会自动注入到 system prompt：

```python
# 在构建 prompt 时
skills_context = await get_active_skills_for_prompt(user_id)
system_prompt = f"{base_prompt}\n\n{skills_context}"
```

Agent 会看到：

```
你已学会以下技能（自动从历史任务中提取）：

- **查询股票实时价格**: 使用 akshare 工具查询 A 股实时价格
  触发条件: 查股价, 股票价格
```

### 技能文档格式

自动生成的技能是 Markdown 格式：

```markdown
# 查询股票实时价格

**名称**: `stock_price_query`

**描述**: 使用 akshare 工具查询 A 股实时价格

---

## 触发条件
当用户请求符合以下模式时，考虑使用此技能：
- 查股价
- 股票价格
- 查询股票

## 执行步骤
1. 解析用户输入的股票代码或名称
2. 调用 akshare_stock_quote 工具
3. 格式化返回结果

## 所需工具
- `akshare_stock_quote`

## 示例用户请求
- "帮我查一下贵州茅台的股价"
- "现在腾讯多少钱一股"

---
*此技能由 AI 自动提取生成*
```

### 数据库结构

**集合**: `auto_skills`

```javascript
{
  "_id": "uuid",
  "user_id": 123,
  "name": "stock_price_query",
  "title": "查询股票实时价格",
  "description": "...",
  "content": "# Markdown 格式的完整文档",
  "trigger_patterns": ["查股价", "股票价格"],
  "required_tools": ["akshare_stock_quote"],
  "examples": ["帮我查一下股价"],
  "confidence": 0.85,
  "source_session_id": "session-uuid",
  "status": "pending" | "active" | "archived",
  "usage_count": 0,
  "created_at": ISODate,
  "updated_at": ISODate,
  "last_used_at": ISODate
}
```

---

## P1: 服务端完整 Agent 循环 🔄

### 核心优势

对比现有的单步模式：

| 特性 | 单步模式（现有） | 完整循环（P1） |
|------|------------------|----------------|
| 执行模式 | 每次 HTTP 请求执行 1 步 | 一次请求执行完整任务 |
| 循环驱动 | 前端 `maxSteps` | 服务端 agentic loop |
| 状态保持 | 每步重建 | 服务端持有完整状态 |
| 后台运行 | 不支持 | 支持断线后继续 |
| 延迟 | 每步需 HTTP 往返 | 无额外往返 |

### 实现文件

1. **`backend/agent_task_service.py`** - 任务状态管理
   - `AgentTask` - 任务数据模型
   - `create_task()` - 创建任务
   - `update_task_status()` - 更新状态
   - `cancel_task()` - 取消任务

2. **`backend/routers/agent_loop.py`** - API 端点
   - `POST /api/agent-loop/start` - 启动任务
   - `GET /api/agent-loop/stream/{task_id}` - SSE 订阅进度
   - `GET /api/agent-loop/status/{task_id}` - 查询状态
   - `POST /api/agent-loop/cancel/{task_id}` - 取消任务
   - `GET /api/agent-loop/list` - 列出任务历史

3. **`agent/core/agent.py`** - 复用现有的 Agent 核心

### 使用流程

#### 1. 启动长任务

```bash
POST /api/agent-loop/start
{
  "session_id": "session-uuid",
  "message": "帮我分析最近三个月的销售数据，生成报表并发送到飞书",
  "model": "claude-opus-4-5",
  "max_iterations": 20
}

# 响应
{
  "task_id": "task-uuid",
  "status": "pending",
  "message": "任务已创建，正在启动..."
}
```

#### 2. 订阅实时进度（SSE）

```javascript
// 前端代码示例
const eventSource = new EventSource(`/api/agent-loop/stream/${taskId}`);

eventSource.addEventListener('status', (e) => {
  const data = JSON.parse(e.data);
  console.log('任务状态:', data.status, data.progress);
});

eventSource.addEventListener('done', (e) => {
  const data = JSON.parse(e.data);
  console.log('任务完成:', data.result);
  eventSource.close();
});

eventSource.addEventListener('error', (e) => {
  const data = JSON.parse(e.data);
  console.error('任务失败:', data.error);
  eventSource.close();
});
```

#### 3. 查询状态（非流式）

```bash
GET /api/agent-loop/status/{task_id}

# 响应
{
  "task_id": "task-uuid",
  "status": "running",
  "progress": 0.6,
  "tool_calls_count": 8,
  "iterations": 4,
  "result": null,
  "error": null,
  "created_at": "2026-07-06T10:00:00Z",
  "updated_at": "2026-07-06T10:05:00Z"
}
```

#### 4. 取消任务

```bash
POST /api/agent-loop/cancel/{task_id}

# 响应
{
  "message": "任务取消请求已发送"
}
```

#### 5. 查看历史

```bash
GET /api/agent-loop/list?session_id=session-uuid&limit=20

# 响应
{
  "tasks": [
    {
      "task_id": "task-uuid",
      "status": "completed",
      "input_text": "帮我分析销售数据...",
      "result": "已完成分析...",
      "tool_calls_count": 12,
      "iterations": 6,
      "created_at": "2026-07-06T10:00:00Z",
      "completed_at": "2026-07-06T10:10:00Z"
    }
  ],
  "total": 1
}
```

### 任务生命周期

```
PENDING → RUNNING → COMPLETED
                  ↘ FAILED
                  ↘ CANCELLED
```

### 后台执行机制

```python
# backend/routers/agent_loop.py

async def _run_agent_loop_background(task, model, max_iterations):
    """在后台运行完整的 Agent 循环"""
    
    # 1. 初始化 Agent
    agent = Agent.create(
        model=model,
        max_iterations=max_iterations,
    )
    
    # 2. 运行完整循环（服务端）
    result = await agent.run(task.input_text)
    
    # 3. 更新任务状态
    await update_task_status(
        task.task_id,
        TaskStatus.COMPLETED,
        result=result.text,
        tool_calls_count=result.tool_calls_made,
    )
    
    # 4. 触发技能提取（P0 集成）
    if result.tool_calls_made >= 5:
        await extract_skill_from_session(...)
```

### 数据库结构

**集合**: `agent_tasks`

```javascript
{
  "_id": "task-uuid",
  "user_id": 123,
  "session_id": "session-uuid",
  "input_text": "用户的原始请求",
  "status": "pending" | "running" | "completed" | "failed" | "cancelled",
  "result": "最终输出结果",
  "error": "错误信息（如果失败）",
  "progress": 0.75,
  "tool_calls_count": 8,
  "iterations": 4,
  "created_at": ISODate,
  "updated_at": ISODate,
  "completed_at": ISODate
}
```

---

## 安装和初始化

### 1. 初始化数据库索引

```bash
cd backend
python init_indexes.py
```

### 2. 重启后端服务

```bash
uvicorn backend.app:app --reload
```

### 3. 验证路由

```bash
# 健康检查
curl http://localhost:8000/api/health

# 列出自动技能
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/auto-skills/list

# 启动 Agent 循环
curl -X POST http://localhost:8000/api/agent-loop/start \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session",
    "message": "测试任务",
    "model": "claude-opus-4-5"
  }'
```

---

## 前端集成建议

### 1. 技能管理界面

创建一个 "我的技能" 页面：

```typescript
// components/SkillsManager.tsx

export function SkillsManager() {
  const [skills, setSkills] = useState([]);

  useEffect(() => {
    fetch('/api/auto-skills/list')
      .then(res => res.json())
      .then(data => setSkills(data.skills));
  }, []);

  const handleConfirm = async (skillId: string, approved: boolean) => {
    await fetch(`/api/auto-skills/${skillId}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved }),
    });
    // 刷新列表
  };

  return (
    <div>
      {skills.map(skill => (
        <SkillCard 
          key={skill.id} 
          skill={skill} 
          onConfirm={handleConfirm} 
        />
      ))}
    </div>
  );
}
```

### 2. 长任务界面

在聊天界面添加 "后台运行" 选项：

```typescript
// components/ChatInput.tsx

const [useBackgroundMode, setUseBackgroundMode] = useState(false);

const handleSubmit = async (message: string) => {
  if (useBackgroundMode) {
    // 使用服务端循环
    const res = await fetch('/api/agent-loop/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        message,
        model: 'claude-opus-4-5',
      }),
    });
    const { task_id } = await res.json();
    
    // 订阅进度
    subscribeToTask(task_id);
  } else {
    // 使用现有的单步模式
    useChat({ ... });
  }
};
```

---

## 与 Hermes 的对比

| 特性 | Hermes | 你的项目（实现后） |
|------|--------|-------------------|
| 自动技能生成 | ✅ | ✅ |
| 跨会话记忆 | ✅ | ✅ |
| 服务端循环 | ✅ | ✅ |
| 后台任务 | ✅ | ✅ |
| 技能确认机制 | ✅ | ✅ |
| 任务取消 | ✅ | ✅ |
| SSE 实时推送 | ✅ | ✅ |
| 工具数量 | 70+ | 15+ |
| 消息平台 | 20+ | 2 |

**核心差距已消除！** 🎉

---

## 后续优化建议

### 短期（1-2 周）

1. **前端集成** - 创建技能管理和长任务界面
2. **测试覆盖** - 为核心功能添加单元测试
3. **性能监控** - 添加任务执行时间、成功率统计

### 中期（1 个月）

1. **记忆向量化** - 将 `memory_service.py` 升级为语义检索
2. **技能推荐** - 在用户输入时智能推荐相关技能
3. **WebSocket 支持** - 替代 SSE，支持双向通信

### 长期（3 个月+）

1. **容器化部署** - Docker + Kubernetes
2. **分布式任务队列** - 使用 Celery 或 Redis Queue
3. **更多消息平台** - Slack、Discord、Telegram 等

---

## 常见问题

### Q: 技能提取会消耗很多 token 吗？

A: 每次提取约消耗 500-1500 tokens（取决于对话长度）。只有 5+ 工具调用的复杂任务才会触发，日常使用影响不大。

### Q: 服务端循环会阻塞其他请求吗？

A: 不会。任务在后台 asyncio.Task 中运行，不影响其他请求。

### Q: 如何控制自动生成的技能质量？

A: 
1. 设置 `confidence` 阈值，只保留高置信度的技能
2. 需要用户手动确认后才激活
3. 可以随时归档不需要的技能

### Q: 单步模式和完整循环可以共存吗？

A: 可以！现有的单步模式（`/api/chat`）保持不变，新增的完整循环（`/api/agent-loop`）是独立的端点。

---

## 总结

通过 P0 和 P1 的实现，你的项目现在具备了：

✅ **自我改进能力** - Agent 会从经验中学习  
✅ **服务端完整循环** - 支持长任务和后台运行  
✅ **任务状态管理** - 可查询、取消、恢复  
✅ **实时进度推送** - SSE 流式更新  
✅ **用户控制** - 技能需确认、任务可取消  

这两个特性是 Hermes 的核心差异化优势，现在你也拥有了！🚀
