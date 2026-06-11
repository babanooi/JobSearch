"""v0.15 JD 质量过滤测试."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


VALID_JD = (
    "岗位职责：负责公司内部平台的后端开发与维护。"
    "任职要求：本科及以上学历，计算机相关专业。"
    "需要 Python、FastAPI、MySQL，有后端项目或实习经历优先。"
    "具备良好的沟通协作能力。熟悉Docker部署。有3年以上工作经验优先。"
)

WELFARE_JD = (
    "我们是一家充满活力的创业公司！五险一金、年终奖、带薪年假、节日福利、团建活动。"
    "下午茶无限供应、健身房、班车、加班补贴、股票期权。扁平管理、弹性工作。"
    "加入我们，一起改变世界！点击申请立即投递！"
)

SHORT_JD = "招人"

AD_JD = "点击申请扫码报名限时优惠免费试听课程介绍培训报名链接"


def test_valid_jd_passes():
    """有职责和要求的 JD 保留"""
    from services.jd_quality_service import judge_jd_quality
    result = judge_jd_quality(VALID_JD, job_name="Python后端")
    assert result["is_valid"] is True
    assert result["quality_score"] >= 40


def test_short_jd_rejected():
    """太短 JD 被过滤"""
    from services.jd_quality_service import judge_jd_quality
    result = judge_jd_quality(SHORT_JD)
    assert result["is_valid"] is False
    assert "过短" in result["quality_reasons"][0]


def test_welfare_jd_rejected():
    """纯福利/广告文本被过滤"""
    from services.jd_quality_service import judge_jd_quality
    result = judge_jd_quality(WELFARE_JD)
    assert result["is_valid"] is False


def test_ad_jd_rejected():
    """纯广告被过滤"""
    from services.jd_quality_service import judge_jd_quality
    result = judge_jd_quality(AD_JD)
    assert result["is_valid"] is False


def test_irrelevant_jd_low_score():
    """与岗位不相关 JD 降分"""
    from services.jd_quality_service import judge_jd_quality
    relevant = judge_jd_quality(VALID_JD, job_name="Python后端")
    irrelevant = judge_jd_quality(VALID_JD, job_name="前端开发")
    # 不相关 JD 的分数应低于相关 JD
    assert irrelevant["quality_score"] <= relevant["quality_score"]


def test_duplicate_jd_filtered():
    """重复 JD 去重"""
    from services.jd_quality_service import filter_jd_items
    items = [{"text": VALID_JD, "title": "test", "company": "A"}, {"text": VALID_JD, "title": "test2", "company": "B"}]
    valid, filtered, summary = filter_jd_items(items)
    assert len(valid) == 1
    assert summary["filtered"] >= 1


def test_quality_score_range():
    """quality_score 在 0-100"""
    from services.jd_quality_service import judge_jd_quality
    for text in ["", "短", VALID_JD, WELFARE_JD]:
        result = judge_jd_quality(text)
        assert 0 <= result["quality_score"] <= 100


def test_quality_level_classification():
    """quality_level 正确分类"""
    from services.jd_quality_service import judge_jd_quality
    result = judge_jd_quality(VALID_JD)
    assert result["quality_level"] in ("high", "medium", "low")


def test_filter_returns_summary():
    """filter_jd_items 返回质量摘要"""
    from services.jd_quality_service import filter_jd_items
    items = [{"text": VALID_JD}, {"text": SHORT_JD}]
    valid, filtered, summary = filter_jd_items(items)
    assert "total" in summary
    assert "valid" in summary
    assert "filtered" in summary
    assert "avg_quality_score" in summary


def test_filter_no_write_to_data():
    """过滤不写入 data/ 目录"""
    from services.jd_quality_service import filter_jd_items
    items = [{"text": VALID_JD}]
    filter_jd_items(items)
    import os
    data_dir = Path(__file__).resolve().parent.parent / "data"
    if data_dir.exists():
        new_files = [f for f in os.listdir(data_dir) if "quality" in f.lower()]
        assert len(new_files) == 0
