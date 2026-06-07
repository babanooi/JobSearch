# JobSearch 产品规划 — 技能差距分析 MVP

## 一、产品定义

### 产品定位

**"先看市场，再投简历"** — 数据驱动的求职技能差距分析工具

### 一句话描述

输入目标岗位，系统基于真实招聘数据告诉你"市场需要什么"，再对比你的技能告诉你"还缺什么"。

### 核心价值主张

| 维度 | 传统方式 | JobSearch |
|------|----------|-----------|
| 信息来源 | 网上经验帖、培训班推荐 | 真实招聘数据统计 |
| 分析方式 | 主观判断、跟风学习 | 数据驱动、量化匹配 |
| 输出结果 | "你应该学XX" | "你缺XX，优先级是XX，市场要求率XX%" |
| 决策依据 | 别人说的 | 数据证明的 |

---

## 二、当前状态

### 已实现

| 功能 | API | 实现位置 |
|------|-----|----------|
| 岗位列表查询 | `GET /skill_rank/_jobs` | `memory/long_term.py` |
| 岗位技能排名 | `GET /skill_rank/{job_name}` | `memory/long_term.py` |
| 技能差距分析 | `POST /skill_gap` | `services/skill_gap.py` |

### 现有 API 分析

**`POST /skill_gap` 已有能力：**

```json
// 请求
{
  "job_name": "Python后端",
  "user_skills": ["Python", "MySQL", "Git"],
  "top_n": 15
}

// 响应
{
  "code": 200,
  "job_name": "Python后端",
  "market_skills": [{"skill": "Python", "count": 95, "total_jds": 100}, ...],
  "matched_skills": [{"skill": "Python", "count": 95, "total_jds": 100}, ...],
  "missing_skills": [{"skill": "Redis", "count": 71, "total_jds": 100}, ...],
  "coverage_ratio": 0.2,
  "priority_order": ["Redis", "Docker", "FastAPI", ...],
  "summary": "「Python后端」市场 Top15 技能中，你已掌握 3 个（覆盖率 20%），缺口 12 个。建议优先学习：Redis、Docker、FastAPI、Linux、Nginx。"
}
```

**核心逻辑（`services/skill_gap.py`）：**
- 从 `job_skills` 表获取市场技能排名
- 归一化用户技能（别名匹配）
- 计算匹配/缺口
- 输出覆盖率 + 优先级

---

## 三、后端 API 规划

### API 总览

| 方法 | 路径 | 用途 | 状态 |
|------|------|------|------|
| `GET` | `/skill_rank/_jobs` | 获取已分析岗位列表 | ✅ 已有 |
| `GET` | `/skill_rank/{job_name}` | 获取岗位技能排名 | ✅ 已有 |
| `POST` | `/skill_gap` | 技能差距分析 | ✅ 已有 |
| `POST` | `/analyze_job` | 触发岗位分析（无数据时） | ✅ 已有 |
| `GET` | `/stats` | 统计信息 | ✅ 已有 |

### API 1：获取岗位列表

**`GET /skill_rank/_jobs`**

用于前端展示"热门岗位"选择。

```json
// 响应
{
  "code": 200,
  "jobs": ["Python后端", "数据分析", "前端开发", "Java开发", ...]
}
```

**前端用途**：首页热门岗位标签、搜索下拉建议

---

### API 2：获取岗位技能排名

**`GET /skill_rank/{job_name}?top_n=15`**

用于前端展示"市场技能列表"，用户在此基础上勾选。

```json
// 响应
{
  "code": 200,
  "data": [
    {"skill": "Python", "count": 95, "total_jds": 100},
    {"skill": "MySQL", "count": 82, "total_jds": 100},
    {"skill": "Redis", "count": 71, "total_jds": 100},
    ...
  ],
  "total_jds": 100,
  "last_update": "2024-06-01 12:00"
}
```

**前端用途**：
- 技能勾选页展示市场技能列表
- 每个技能显示"XX% 的岗位要求"
- 用户勾选自己会的技能

**需要前端计算的字段：**
```javascript
// 前端计算市场要求率
market_rate = (skill.count / total_jds * 100).toFixed(0) + "%"
```

---

### API 3：技能差距分析

**`POST /skill_gap`**

核心 API，计算用户技能与市场需求的差距。

```json
// 请求
{
  "job_name": "Python后端",
  "user_skills": ["Python", "MySQL", "Git"],
  "top_n": 15
}

// 响应
{
  "code": 200,
  "job_name": "Python后端",
  "market_skills": [...],      // 市场 Top N 技能
  "matched_skills": [...],     // 用户已掌握的
  "missing_skills": [...],     // 用户缺少的
  "coverage_ratio": 0.2,       // 覆盖率（0-1）
  "priority_order": [...],     // 建议学习顺序（前5个）
  "summary": "..."             // 文字摘要
}
```

**前端展示映射：**

| 响应字段 | 前端展示 |
|----------|----------|
| `coverage_ratio` | 匹配度仪表盘（百分比） |
| `matched_skills` | "你已掌握的技能"列表 |
| `missing_skills` | "你缺少的技能"列表 |
| `priority_order` | "学习优先级"建议 |

---

### API 4：触发岗位分析

**`POST /analyze_job`**

当用户搜索的岗位在数据库中不存在时，触发实时分析。

```json
// 请求
{
  "job_name": "Go后端"
}

// 响应（异步）
{
  "code": 200,
  "task_id": "xxx",
  "thread_id": "xxx",
  "async": true
}
```

**配合 `GET /task/{task_id}` 查询进度。**

**前端交互流程：**
```
用户搜索"Go后端"
    │
    ▼
前端调用 GET /skill_rank/Go后端
    │
    ▼
返回空数据 → 提示"该岗位暂无数据，是否立即分析？"
    │
    ▼
用户确认 → 调用 POST /analyze_job
    │
    ▼
轮询 GET /task/{task_id} 直到完成
    │
    ▼
重新调用 GET /skill_rank/Go后端 获取数据
```

---

## 四、前端接入指南

### 前端落地方式

当前项目已经有 `ui/static/index.html`、`ui/static/app.js`、`ui/static/style.css` 组成的 Vanilla JS SPA，并且已有对话、技能雷达、深度研究、用户中心四个视图。MVP 不需要另起 React/Vue/Next.js 项目，优先在现有 SPA 内新增一个“技能差距”视图，复用当前导航、请求封装、Toast、暗色视觉系统和岗位标签能力。

| 技术 | 当前选择 | 原因 |
|------|----------|------|
| 页面架构 | 现有 Vanilla JS SPA | 改动小，适合作为简历展示稳定版的产品化迭代 |
| UI 系统 | 复用 `style.css` | 保持 JobLab 现有视觉一致性 |
| 状态管理 | 页面内状态 + DOM | MVP 状态简单，无需引入框架 |
| HTTP | Fetch | 已在项目中使用，继续沿用 |

### 前端页面结构

```
现有 SPA 视图
├── chat       # 智能对话
├── radar      # 技能雷达：展示岗位市场技能
├── gap        # 技能差距：岗位选择 -> 技能勾选 -> 差距结果
├── research   # 深度研究
└── user       # 用户中心
```

### 技能差距交互流程

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  Step 1: 选择岗位                                           │
│  ┌─────────────────────────────────────────┐                │
│  │  调用: GET /skill_rank/_jobs            │                │
│  │  展示: 热门岗位标签 + 搜索框             │                │
│  │  交互: 点击或搜索后进入 Step 2           │                │
│  └─────────────────────────────────────────┘                │
│              │                                              │
│              ▼                                              │
│  Step 2: 勾选技能                                           │
│  ┌─────────────────────────────────────────┐                │
│  │  调用: GET /skill_rank/{job_name}       │                │
│  │  展示: 技能列表 + 勾选框                 │                │
│  │  计算: market_rate = count/total_jds    │                │
│  │  交互: 勾选后点击"开始分析"              │                │
│  └─────────────────────────────────────────┘                │
│              │                                              │
│              ▼                                              │
│  Step 3: 查看结果                                           │
│  ┌─────────────────────────────────────────┐                │
│  │  调用: POST /skill_gap                  │                │
│  │  展示: 匹配度 + 差距详情 + 学习建议       │                │
│  │  交互: 重新分析 / 换个岗位               │                │
│  └─────────────────────────────────────────┘                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 前端需要处理的逻辑

**1. 市场要求率计算**
```javascript
// 后端返回 count 和 total_jds，前端计算百分比
const marketRate = Math.round(skill.count / totalJds * 100);
```

**2. 优先级标签**
```javascript
// 根据 market_rate 显示优先级标签
const getPriority = (rate) => {
  if (rate >= 60) return { label: '高优先', color: 'red' };
  if (rate >= 40) return { label: '中优先', color: 'yellow' };
  return { label: '低优先', color: 'green' };
};
```

**3. 匹配度状态**
```javascript
// 根据 coverage_ratio 显示状态
const getStatus = (ratio) => {
  if (ratio >= 0.7) return { label: '竞争力强', color: 'green' };
  if (ratio >= 0.4) return { label: '需要提升', color: 'yellow' };
  return { label: '差距较大', color: 'red' };
};
```

**4. 无数据时自动触发分析流程**
```javascript
// GET /skill_rank/{job_name} 返回空数据时
if (!data || data.length === 0) {
  // 显示"立即分析岗位"按钮（非弹窗确认，页面内按钮）
  // 用户点击后：
  // 1. 调用 POST /analyze_job → 返回 task_id
  // 2. 轮询 GET /task/{task_id}（每2秒，最多6分钟）
  // 3. 展示进度文字（从 task.progress 获取）
  // 4. 完成后自动重新调用 GET /skill_rank/{job_name}
  // 5. 成功则展示技能勾选列表
  // 6. 失败或超时则显示错误信息
}
```

### 内容策略落点

`/skill_gap` 的结果不只展示“缺什么”，还应该形成用户下一步行动的内容入口：

| 结果字段 | 内容表达 | 后续可扩展 |
|----------|----------|------------|
| `matched_skills` | 已具备技能，用于增强信心和简历表达 | 简历亮点生成 |
| `missing_skills` | 缺口技能，按市场频次排序 | 学习路线、题单、项目建议 |
| `priority_order` | 前 5 个优先补齐技能 | 内容库推荐、学习计划 |
| `summary` | 一句话诊断 | 分享卡片、历史记录 |

V1.1 先做“诊断结果 + 学习优先级”，V2 再接学习资源库，避免在数据闭环没跑通前堆内容。

---

## 五、目标用户

### 主要用户画像

**用户A：转行求职者**
- 痛点：不知道目标岗位真正需要什么技能
- 场景：想从测试转数据分析，但不知道学什么
- 期望：明确知道"还差什么"，不浪费时间学没用的

**用户B：应届毕业生**
- 痛点：简历写满了技术，但不知道哪些值钱
- 场景：学了Python、Java、C++，但不确定哪个更匹配目标岗位
- 期望：知道优先展示哪些技能，重点准备什么

**用户C：在职跳槽者**
- 痛点：想知道自己的技能在市场上值多少
- 场景：做了3年后端，想知道跳槽需要补什么
- 期望：量化自己的市场竞争力

---

## 六、MVP 范围

### 后端（当前阶段）

| 任务 | 状态 | 说明 |
|------|------|------|
| `GET /skill_rank/_jobs` | ✅ 已完成 | 岗位列表 |
| `GET /skill_rank/{job_name}` | ✅ 已完成 | 技能排名 |
| `POST /skill_gap` | ✅ 已完成 | 差距分析 |
| `POST /analyze_job` | ✅ 已完成 | 触发分析 |
| `GET /task/{task_id}` | ✅ 已完成 | 任务状态 |
| `GET /stats` | ✅ 已完成 | 统计信息 |

**后端 API 已基本就绪，可直接供前端接入。**

### 前端（下一阶段）

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 岗位选择页面 | P0 | 搜索 + 热门推荐 |
| 技能勾选页面 | P0 | 市场技能列表 + 勾选 |
| 差距分析结果页 | P0 | 匹配度 + 差距详情 |
| 无数据处理 | P0 | 触发分析 + loading |
| 响应式布局 | P1 | 移动端适配 |
| 历史记录 | P2 | 本地存储或后端支持 |

### 不包含

| 功能 | 推迟版本 | 原因 |
|------|----------|------|
| 用户注册/登录 | V2 | MVP无需账号体系 |
| 数据库存储用户技能 | V2 | 前端传参即可 |
| 技能趋势对比 | V2 | 需要历史数据 |
| 学习资源推荐 | V2 | 需要内容库 |
| 分享/PDF导出 | V2 | 非核心 |

---

## 七、数据流

### 完整数据流

```
用户浏览器
    │
    ├─ GET /skill_rank/_jobs ──────────► 返回岗位列表
    │
    ├─ GET /skill_rank/Python后端 ────► 返回技能排名
    │   (前端计算 market_rate)
    │
    ├─ 用户勾选技能 ──────────────────► 前端收集 user_skills
    │
    └─ POST /skill_gap ──────────────► 返回差距分析结果
        │
        ├─ market_skills (市场技能)
        ├─ matched_skills (已掌握)
        ├─ missing_skills (缺少)
        ├─ coverage_ratio (匹配度)
        ├─ priority_order (学习优先级)
        └─ summary (文字摘要)
```

### 无数据时自动分析流程

```
用户搜索"Go后端"
    │
    ├─ GET /skill_rank/Go后端 ────────► 返回空 []
    │
    ├─ 页面内显示"立即分析岗位"按钮（非弹窗）
    │
    ├─ 用户点击按钮
    │
    ├─ POST /analyze_job ─────────────► 返回 task_id
    │
    ├─ 轮询 GET /task/{task_id} ──────► 实时显示进度文字（最多6分钟）
    │
    ├─ 任务完成 ──────────────────────► 自动重新加载技能列表
    │
    └─ GET /skill_rank/Go后端 ────────► 返回技能排名 → 展示勾选列表
```

---

## 八、成功指标

### 后端阶段（当前）

| 指标 | 目标 | 衡量方式 |
|------|------|----------|
| API 可用性 | 100% | 所有端点正常响应 |
| 响应时间 | <2s | /skill_gap 平均耗时 |
| 数据覆盖 | 10+ 岗位 | job_skills 表岗位数 |

### 产品上线后（1个月）

| 指标 | 目标 | 衡量方式 |
|------|------|----------|
| 完成分析用户 | 50+ | /skill_gap 调用次数 |
| 分析完成率 | 80%+ | 进入分析→完成的比例 |
| 岗位覆盖 | 20+ | 已分析岗位数 |

---

## 九、迭代路线图

### V1.0 — 后端 API MVP（当前）

- [x] 岗位列表 API
- [x] 技能排名 API
- [x] 差距分析 API
- [x] 触发分析 API
- [ ] API 文档（Swagger/OpenAPI）

### V1.1 — 现有 SPA 技能差距闭环

- [x] 后端 `/skill_gap` 参数校验与鲁棒性
- [x] 新增技能差距导航入口
- [x] 岗位选择与热门岗位标签
- [x] 市场技能勾选与自定义技能输入
- [x] 差距分析结果页
- [x] 无数据自动触发分析流程（/analyze_job → /task/{id} → /skill_rank/{name}）
- [x] 历史会话删除实时更新（deletedThreads 集合防异步回显）
- [x] 技能数据质量基础过滤（is_low_quality_skill 过滤泛词/动词/过短词）
- [x] 数据置信度提示（high/medium/low 三级）
- [ ] 部署上线

### product-mvp-v0.3 — 技能数据质量治理

- [x] 技能 taxonomy 规则中心化（`tools/skill_taxonomy.py`）
- [x] 抽取 prompt 加强：只提取可执行硬技能，排除泛领域词/岗位名/职责动词
- [x] 搜索结果来源质量评分：过滤明显不像招聘 JD 的结果
- [x] 入库前复用 taxonomy 过滤，减少坏技能进入 `job_skills`
- [x] `/skill_gap` 输出技能项增加单项 `confidence` 和 `quality_reasons`
- [x] 新增离线评估脚本：`scripts/evaluate_skill_quality.py`
- [x] 新增 taxonomy 单元测试，覆盖 AI 产品经理泛词问题
- [x] `/skill_rank` 输出层质量治理：复用 `filter_market_skills` + `estimate_market_confidence`
- [x] 技能差距勾选列表不再直接暴露低质量泛词（AI、人工智能、计算机科学等）
- [x] `filtered_count` 和 `confidence` 用于前端解释数据可信度
- [x] 公共函数 `filter_market_skills` + `estimate_market_confidence` 供 `/skill_rank` 和 `/skill_gap` 共用
- [x] 技能质量人工反馈闭环（v0.4 localStorage 临时方案 → v0.5 后端闭环）：
  - POST /skill_feedback：用户标记 reject/important，upsert 去重
  - GET /skill_feedback/summary：按岗位聚合社区反馈数量
  - /skill_rank 返回 feedback 标记：reject_count、important_count、user_rejected、community_rejected
  - 前端按钮调后端 API，localStorage 仅作网络失败兜底
  - 社区 reject ≥3 的技能降权显示，重要 ≥3 标记"多人标记"
  - 反馈摘要区域显示社区标记数量
  - 反馈数据进入数据库，可作为 taxonomy 迭代样本来源

### product-mvp-v0.5 — 技能反馈后端闭环

- [x] 新增 `skill_feedback` 数据表（user_id, job_name, skill_name, action, created_at）
- [x] POST `/skill_feedback` API（upsert 去重）
- [x] GET `/skill_feedback/summary` API（按岗位聚合社区反馈）
- [x] `/skill_rank` 返回 feedback 标记（reject_count, community_rejected 等）
- [x] 前端按钮调后端 API，localStorage 降级为兜底
- [x] 社区 reject ≥3 降权，重要 ≥3 标记"多人标记"
- [x] 移除"导出反馈"主按钮，隐藏为 debug 入口
- [x] localStorage 反馈仅在网络失败时临时保存

### product-mvp-v0.6 — 简历解析与用户技能画像

- [x] 新增简历/经历文本解析服务 `services/resume_profile.py`
- [x] 支持 TXT/MD/CSV、可复制文本 PDF、DOCX 的文本提取，图片简历/OCR 暂不纳入本轮
- [x] 新增 `POST /profile/resume_text`：从粘贴的简历或经历文本生成技能画像
- [x] 新增 `POST /profile/resume`：从上传简历文件生成技能画像
- [x] LLM 抽取失败时使用 taxonomy 规则兜底，保证无模型环境下仍可得到基础技能线索
- [x] `/skill_gap` 支持 `user_profile` 参数，将画像技能与手动技能合并后计算差距
- [x] 前端技能差距页新增"简历技能画像"区域，用户可粘贴/上传简历并移除误识别技能
- [x] 用户手动勾选从主输入方式降级为修正方式，产品逻辑从"你会什么"转为"系统先读懂你"

### product-mvp-v0.7 — 岗位画像、候选人画像与初筛模拟

- [x] 新增 `services/screening.py`，将画像和初筛逻辑从技能差距服务中拆出
- [x] 岗位画像 `JobProfile`：识别岗位类型、面向人群、学历要求、专业要求、经验要求、硬技能、业务领域、软性要求
- [x] 候选人画像 `CandidateProfile`：识别教育背景、专业、毕业年份、实习/工作经历、项目经历、量化成果和技能证据
- [x] 初筛报告 `MatchReport`：按技能、学历、专业、经历、证据五个维度评分，并输出通过风险、可能被筛原因、简历改写建议
- [x] 新增 `GET /job_profile/{job_name}`、`POST /candidate_profile`、`POST /screening_report`
- [x] 技能差距页优先展示"岗位画像 / 候选人画像"两张卡片，再展示初筛风险、缺口建议和技能匹配明细
- [x] 明确不使用年龄作为评分依据，只使用经验阶段、毕业年份和经历证据进行匹配判断

### V2.0 — 功能扩展

- [ ] 用户注册/登录
- [ ] 历史分析记录（数据库存储）
- [ ] 技能趋势对比
- [ ] 学习资源推荐
- [ ] 分享功能

### V3.0 — 商业化

- [ ] 高级分析功能
- [ ] API 开放
- [ ] 付费订阅
- [ ] B端合作

---

## 十、技能数据质量治理

### 当前问题

关键词抽取（LLM extract）会产生大量泛词：
- 过宽泛领域词：AI、IOT、NLP、前端、算法
- 动词/动作词：清洗、重构、辅导、测试
- 过短无意义词：api、net、Go
- 行业大类：计算机科学、软件工程、深度学习

这些词如果直接展示在技能差距页面，会误导用户以为"需要学 AI"是具体可执行的建议。

### 本轮实现（基础过滤）

1. **`is_low_quality_skill()`**：规则过滤，包括：
   - 过短词（≤2 字符，排除已知缩写）
   - 过宽泛领域大类词（30+ 个）
   - 动词/动作词（15+ 个）
   - 岗位名模式（≤4 字 + 开发/工程师/岗位/实习）

2. **置信度评估**：
   - `high`：过滤后 ≥5 个技能，且 JD 样本 ≥5
   - `medium`：过滤比例 >30%
   - `low`：过滤后 <5 个技能或 JD 样本 <5

3. **前端提示**：
   - 置信度 low：黄色提示"当前岗位数据样本较少，结果仅供参考"
   - 置信度 medium：灰色提示"部分泛词已被过滤，结果基本可信"
   - 置信度 high：绿色提示"数据置信度较高"

### 后续迭代

| 方案 | 优先级 | 说明 |
|------|--------|------|
| 技能词典白名单 | P0 | 已建立 taxonomy 初版，后续扩充词表 |
| 岗位类型分类 | P1 | 已支持 backend/frontend/data/ai/product/test/embedded 初版 |
| 人工校验入口 | P2 | 允许用户标记"这个不是技能" |
| 数据源质量评分 | P2 | 已做搜索结果 JD 相关性评分，后续按来源和公司可信度加权 |

### v0.3 本轮实现

1. **taxonomy 中心化**：新增 `tools/skill_taxonomy.py`，统一维护泛词、动作词、岗位名模式、已知技能、岗位类别和质量置信度。
2. **抽取前约束**：`ExtractAgent` prompt 明确要求只输出可执行技能，并针对产品经理保留 PRD、Axure、需求分析、竞品分析、SQL 等能力。
3. **来源质量评分**：`tools/search.py` 对搜索结果打 `source_quality`，过滤培训/百科/教程等弱 JD 结果。
4. **入库前过滤**：`guard_skill_list()` 复用 taxonomy，减少坏技能进入 `job_skills`。
5. **展示层透传**：`/skill_gap` 的每个市场技能带 `confidence` 和 `quality_reasons`，便于前端或评估脚本解释结果。
6. **离线评估**：`scripts/evaluate_skill_quality.py` 可统计坏词率、低质量样本和高风险岗位。

---

## 十一、风险与应对

| 风险 | 影响 | 应对方案 |
|------|------|----------|
| 岗位覆盖不足 | 用户搜不到 | 支持触发实时分析 |
| 技能匹配不准确 | 归一化问题 | 完善别名表 + 语义匹配 |
| 技能数据泛词多 | 误导用户 | 基础过滤 + 置信度提示（已实现） |
| 分析耗时过长 | 用户等待 | 异步任务 + 进度提示 |
| 市场数据过时 | 分析不准 | 定期更新数据 |

---

## 十一、下一步行动

### 立即执行

1. [x] 确认后端 API 满足前端需求
2. [x] 在现有 SPA 接入技能差距分析
3. [ ] 补充 Swagger/OpenAPI 示例
4. [ ] 本地服务 smoke test + Git tag

### 待确认

- [x] 后端 API 是否需要调整？
- [x] 前端技术栈选择？
- [ ] 部署方案？
