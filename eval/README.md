# Golden Set 评测框架

## 什么是 Golden Set

Golden Set 是一组人工标注的标准评测样本，用于评估系统输出质量。

每个 case 包含：
- 输入：岗位名 + JD 文本 + 简历文本
- 标准答案：gold_job_profile / gold_candidate_profile / gold_fit

评测脚本自动运行系统，将输出与标准答案做关键词匹配，计算命中率。

**注意**：这不是训练，不是 LoRA，只是质量回归检查。

## 如何新增 case

编辑 `eval/golden_set_v1.json`，每个 case 必须包含：

```json
{
  "case_id": "case_006",
  "job_name": "岗位名",
  "jd_texts": ["JD文本1", "JD文本2"],
  "resume_text": "简历文本",
  "gold_job_profile": {
    "employment_type": "全职",
    "must_have_capabilities": ["Python", "FastAPI"],
    ...
  },
  "gold_candidate_profile": {
    "skill_keywords": ["Python", "MySQL"],
    "project_keywords": ["项目名", "技术栈"],
    ...
  },
  "gold_fit": {
    "overall_fit_level": "strong/moderate/weak",
    "expected_strengths": ["优势1"],
    "expected_gaps": ["差距1"],
    "expected_learning_keywords": ["学习1"],
    ...
  },
  "notes": "说明"
}
```

标准答案尽量包含可匹配的关键词，不要太模糊。

## 如何运行

```bash
# 使用规则 fallback（默认，不调 LLM）
python eval/run_golden_eval.py

# 调用真实 FitAnalysisAgent
python eval/run_golden_eval.py --use-agent

# 只跑前 2 个 case
python eval/run_golden_eval.py --limit 2

# 指定输出路径
python eval/run_golden_eval.py --output eval/reports/my_report.json
```

## 如何解读分数

| 指标 | 含义 |
|------|------|
| `job_profile_score` | 岗位画像与标准答案的关键词命中率 (0-100) |
| `candidate_profile_score` | 候选人画像与标准答案的关键词命中率 (0-100) |
| `fit_level_match` | 适配等级是否与标准答案一致 |
| `strengths_hit_rate` | 优势关键词命中率 |
| `gaps_hit_rate` | 差距关键词命中率 |
| `learning_plan_hit_rate` | 学习计划关键词命中率 |
| `hallucination_flags` | 系统输出中有标准答案没有的关键词 |

通过标准：总分 >= 50 且 fit_level_match = true

## 当前限制

- 关键词匹配，不是语义匹配
- 标准答案是合成数据，不是真实人工标注
- 评测不覆盖前端展示
- 不做 LoRA 微调
