"""Golden Set 自动评测脚本 — v0.14

用法：
  python eval/run_golden_eval.py              # 使用规则 fallback
  python eval/run_golden_eval.py --use-agent  # 允许调用真实 Agent
  python eval/run_golden_eval.py --limit 2    # 只跑前 2 个 case
  python eval/run_golden_eval.py --output eval/reports/custom.json
"""
from __future__ import annotations
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _load_golden_set(path: str = None) -> list[dict]:
    p = Path(path) if path else Path(__file__).parent / "golden_set_v1.json"
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _keyword_hit_rate(gold_keywords: list[str], actual_items: list, key: str = "") -> tuple[float, list[str]]:
    """计算关键词命中率，返回 (hit_rate, missed_keywords)"""
    if not gold_keywords:
        return 1.0, []
    actual_set = set()
    for item in actual_items:
        if isinstance(item, str):
            actual_set.add(item.lower())
        elif isinstance(item, dict):
            val = item.get(key or "skill", item.get("name", item.get("description", "")))
            if isinstance(val, str):
                actual_set.add(val.lower())
    hit = 0
    missed = []
    for kw in gold_keywords:
        kw_lower = kw.lower()
        if any(kw_lower in a for a in actual_set):
            hit += 1
        else:
            missed.append(kw)
    return round(hit / len(gold_keywords), 3), missed


def _evaluate_case(case: dict, job_profile: dict, candidate_profile: dict, fit_report: dict) -> dict:
    """对单个 case 做关键词匹配评估"""
    gold_job = case.get("gold_job_profile", {})
    gold_cand = case.get("gold_candidate_profile", {})
    gold_fit = case.get("gold_fit", {})

    # 岗位画像评估
    jp_must_hit, jp_must_miss = _keyword_hit_rate(
        gold_job.get("must_have_capabilities", []),
        job_profile.get("must_have_capabilities", []),
    )
    jp_resp_hit, jp_resp_miss = _keyword_hit_rate(
        gold_job.get("responsibilities_keywords", []),
        job_profile.get("responsibilities", []),
    )
    job_profile_score = round((jp_must_hit * 0.7 + jp_resp_hit * 0.3) * 100, 1)

    # 候选人画像评估
    cand_skill_hit, cand_skill_miss = _keyword_hit_rate(
        gold_cand.get("skill_keywords", []),
        candidate_profile.get("skill_stack", []),
        key="skill",
    )
    cand_proj_hit, cand_proj_miss = _keyword_hit_rate(
        gold_cand.get("project_keywords", []),
        candidate_profile.get("projects", []),
        key="description",
    )
    cand_achieve_hit, cand_achieve_miss = _keyword_hit_rate(
        gold_cand.get("achievement_keywords", []),
        candidate_profile.get("achievements", []),
        key="description",
    )
    candidate_score = round((cand_skill_hit * 0.4 + cand_proj_hit * 0.4 + cand_achieve_hit * 0.2) * 100, 1)

    # 适配分析评估
    fit_level_match = fit_report.get("overall_fit_level") == gold_fit.get("overall_fit_level")

    strengths_hit, strengths_miss = _keyword_hit_rate(
        gold_fit.get("expected_strengths", []),
        fit_report.get("strengths", []),
    )
    gaps_hit, gaps_miss = _keyword_hit_rate(
        gold_fit.get("expected_gaps", []),
        fit_report.get("gaps", []),
    )
    learning_hit, learning_miss = _keyword_hit_rate(
        gold_fit.get("expected_learning_keywords", []),
        fit_report.get("learning_plan", []),
    )

    # 幻觉标记：系统输出中有 gold 里没有的关键词
    hallucination_flags = []
    sys_must = set(s.lower() for s in job_profile.get("must_have_capabilities", []))
    gold_must = set(s.lower() for s in gold_job.get("must_have_capabilities", []))
    for s in sys_must - gold_must:
        hallucination_flags.append(f"job_profile.must_have 多出: {s}")

    total_score = round(job_profile_score * 0.3 + candidate_score * 0.3 + (
        (fit_level_match * 20) + (strengths_hit * 10) + (gaps_hit * 10) + (learning_hit * 10)
    ), 1)

    return {
        "passed": total_score >= 50 and fit_level_match,
        "score": total_score,
        "job_profile_score": job_profile_score,
        "candidate_profile_score": candidate_score,
        "fit_level_match": fit_level_match,
        "strengths_hit_rate": round(strengths_hit * 100, 1),
        "gaps_hit_rate": round(gaps_hit * 100, 1),
        "learning_plan_hit_rate": round(learning_hit * 100, 1),
        "missed_keywords": {
            "job_must_have": jp_must_miss,
            "job_responsibilities": jp_resp_miss,
            "candidate_skills": cand_skill_miss,
            "candidate_projects": cand_proj_miss,
            "fit_strengths": strengths_miss,
            "fit_gaps": gaps_miss,
            "fit_learning": learning_miss,
        },
        "hallucination_flags": hallucination_flags,
        "notes": case.get("notes", ""),
    }


def run_golden_eval(use_agent: bool = False, limit: int = 0, output: str = None) -> dict:
    """运行 Golden Set 评测"""
    cases = _load_golden_set()
    if limit > 0:
        cases = cases[:limit]

    from services.job_profile_service import extract_job_profile
    from services.candidate_profile_service import extract_candidate_profile
    from services.fit_analysis_service import analyze_fit
    from services.profile_schemas import JobProfileResult, CandidateProfileResult

    results = []
    for i, case in enumerate(cases):
        print(f"[{i+1}/{len(cases)}] {case['case_id']}: {case['job_name']}...")

        # 生成岗位画像（使用 case 自带的 jd_texts，不依赖数据库）
        job_profile = extract_job_profile(case["job_name"], top_n=15, raw_jd_texts=case.get("jd_texts", []))
        job_dict = job_profile.model_dump()

        # 生成候选人画像
        cand_profile = extract_candidate_profile(resume_text=case.get("resume_text", ""))
        cand_dict = cand_profile.model_dump()

        # 适配分析（默认规则，可选 Agent）
        fit_report = analyze_fit(job_profile, cand_profile)
        if use_agent:
            try:
                from services.fit_analysis_agent import analyze_fit_with_agent
                fit_report, mode = analyze_fit_with_agent(job_profile, cand_profile, fit_report)
                print(f"  Agent mode: {mode}")
            except Exception as e:
                print(f"  Agent failed, using rule fallback: {e}")

        fit_dict = fit_report.model_dump()

        # 评估
        eval_result = _evaluate_case(case, job_dict, cand_dict, fit_dict)
        eval_result["case_id"] = case["case_id"]
        eval_result["job_name"] = case["job_name"]
        results.append(eval_result)

        status = "PASS" if eval_result["passed"] else "FAIL"
        print(f"  {status} score={eval_result['score']} "
              f"job={eval_result['job_profile_score']} "
              f"cand={eval_result['candidate_profile_score']} "
              f"fit_match={eval_result['fit_level_match']}")

    # 汇总
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    avg_score = round(sum(r["score"] for r in results) / max(1, total), 1)
    avg_job = round(sum(r["job_profile_score"] for r in results) / max(1, total), 1)
    avg_cand = round(sum(r["candidate_profile_score"] for r in results) / max(1, total), 1)
    fit_match_rate = round(sum(1 for r in results if r["fit_level_match"]) / max(1, total) * 100, 1)

    summary = {
        "total_cases": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / max(1, total) * 100, 1),
        "avg_score": avg_score,
        "avg_job_profile_score": avg_job,
        "avg_candidate_profile_score": avg_cand,
        "fit_level_match_rate": fit_match_rate,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "use_agent": use_agent,
    }

    report = {"summary": summary, "cases": results}

    # 写入报告
    out_path = output or str(Path(__file__).parent / "reports" / "golden_eval_latest.json")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 控制台摘要
    print(f"\n{'='*50}")
    print(f"  Golden Set 评测完成")
    print(f"  总数: {total}  通过: {passed}  失败: {total - passed}")
    print(f"  通过率: {summary['pass_rate']}%")
    print(f"  平均分: {avg_score}")
    print(f"  岗位画像平均分: {avg_job}")
    print(f"  候选人画像平均分: {avg_cand}")
    print(f"  适配等级匹配率: {fit_match_rate}%")
    print(f"  报告: {out_path}")
    print(f"{'='*50}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Golden Set 评测脚本")
    parser.add_argument("--use-agent", action="store_true", help="调用真实 FitAnalysisAgent")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 个 case")
    parser.add_argument("--output", type=str, default=None, help="输出路径")
    args = parser.parse_args()

    run_golden_eval(use_agent=args.use_agent, limit=args.limit, output=args.output)
