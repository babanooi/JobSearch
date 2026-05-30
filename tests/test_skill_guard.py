"""技能过滤规则单元测试 —— 基于 eval_report.json 真实坏数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.skill_guard import guard_skill_list, BLOCK_PATTERNS
import re


def test_filters_short_job_titles():
    """≤4字前缀 + 开发/工程师 — 应全被过滤"""
    bad = ["后端开发", "前端开发", "全栈开发", "接口开发",
           "后端工程师", "代码开发"]
    result = guard_skill_list(bad)
    assert result == [], f"应全被过滤，但保留了: {result}"


def test_filters_qualified_job_titles():
    """含限定词的岗位名 — "Web前端开发"、"前后端开发"等"""
    bad = ["Web前端开发", "前后端开发", "服务端开发", "软件界面开发",
           "智能体开发", "爬虫开发", "数据开发"]
    result = guard_skill_list(bad)
    assert result == [], f"应全被过滤，但保留了: {result}"


def test_filters_dev_machine():
    """开发机/环境/服务相关垃圾"""
    bad = ["在线开发机", "在线开发机服务", "远程开发服务", "云端开发环境"]
    result = guard_skill_list(bad)
    assert result == [], f"应全被过滤，但保留了: {result}"


def test_filters_overly_long():
    """超过 30 字的拼接字符串"""
    bad = ["高性能，高并发，分布式，短距无线通信，嵌入式，MEMS，嵌入式数据库，数据库，erlang"]
    result = guard_skill_list(bad)
    assert result == [], f"应被过滤: {result}"


def test_keeps_real_skills():
    """真正的技术技能应保留"""
    good = ["Python", "Django", "FastAPI", "Kubernetes", "RAG",
            "LangChain", "Agent", "MCP", "Prompt Engineering", "LLM",
            "Go", "Rust", "TypeScript", "PostgreSQL", "Redis"]
    result = guard_skill_list(good)
    assert result == good, f"应全部保留，但丢失了: {set(good) - set(result)}"


def test_keeps_testing_skills():
    """自动化测试、单元测试 是合法技能，不应被过滤"""
    good = ["自动化测试", "单元测试", "性能测试", "集成测试"]
    result = guard_skill_list(good)
    assert result == good, f"应全部保留，但丢失了: {set(good) - set(result)}"


def test_filters_from_eval_report():
    """从 eval_report.json 提取的全部 24 个坏数据样例"""
    from json import load
    eval_path = Path(__file__).resolve().parent.parent / "data" / "eval_report.json"
    report = load(open(eval_path, encoding="utf-8"))
    bad_samples = report["issues"]["bad_skills_sample"]
    bad_skills = {s[1] for s in bad_samples}  # skill_name 在位置 1

    filtered = guard_skill_list(list(bad_skills))
    missed = set(filtered)
    if missed:
        print(f"\n  警告：仍有 {len(missed)} 个 bad skill 未被过滤:")
        for s in missed:
            print(f"    - {s}")
    # 目标是 100% 过滤率
    assert len(missed) == 0, f"{len(missed)} 个坏技能漏过滤: {missed}"
