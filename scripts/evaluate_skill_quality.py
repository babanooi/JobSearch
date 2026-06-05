"""Evaluate quality of skill data in job_skills.

Usage:
  python scripts/evaluate_skill_quality.py
  python scripts/evaluate_skill_quality.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.database import SessionLocal
from sqlalchemy import text
from tools.skill_taxonomy import assess_skill_quality, infer_job_family


def load_rows() -> list[dict]:
    with SessionLocal() as session:
        rows = session.execute(
            text(
                "SELECT job_name, skill_name, count, total_jds "
                "FROM job_skills ORDER BY job_name, count DESC"
            )
        ).fetchall()
    return [
        {
            "job_name": row[0],
            "skill_name": row[1],
            "count": int(row[2] or 0),
            "total_jds": int(row[3] or 0),
        }
        for row in rows
    ]


def build_report(rows: list[dict]) -> dict:
    total = len(rows)
    rejected = []
    confidence = Counter()
    families = Counter()
    jobs = defaultdict(lambda: {"total": 0, "rejected": 0, "low": 0})

    for row in rows:
        job = row["job_name"]
        family = infer_job_family(job)
        meta = assess_skill_quality(row["skill_name"], job_name=job)
        families[family] += 1
        jobs[job]["total"] += 1
        if not meta["accepted"]:
            jobs[job]["rejected"] += 1
            rejected.append({**row, "reasons": meta["reasons"], "category": meta["category"]})
        else:
            confidence[meta["confidence"]] += 1
            if meta["confidence"] == "low":
                jobs[job]["low"] += 1

    bad_rate = round(len(rejected) / total, 4) if total else 0.0
    risky_jobs = sorted(
        (
            {
                "job_name": job,
                "total": stat["total"],
                "rejected": stat["rejected"],
                "bad_rate": round(stat["rejected"] / stat["total"], 4) if stat["total"] else 0,
            }
            for job, stat in jobs.items()
        ),
        key=lambda x: (x["bad_rate"], x["rejected"]),
        reverse=True,
    )

    return {
        "total_skills": total,
        "accepted_skills": total - len(rejected),
        "rejected_skills": len(rejected),
        "bad_rate": bad_rate,
        "confidence": dict(confidence),
        "job_families": dict(families),
        "rejected_sample": rejected[:30],
        "risky_jobs": risky_jobs[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args()

    report = build_report(load_rows())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=== Skill Quality Report ===")
        print(f"total_skills: {report['total_skills']}")
        print(f"accepted_skills: {report['accepted_skills']}")
        print(f"rejected_skills: {report['rejected_skills']}")
        print(f"bad_rate: {report['bad_rate']:.1%}")
        print(f"confidence: {report['confidence']}")
        print("\n-- rejected sample --")
        for item in report["rejected_sample"][:10]:
            print(f"{item['job_name']} | {item['skill_name']} | {','.join(item['reasons'])}")
        print("\n-- risky jobs --")
        for item in report["risky_jobs"][:10]:
            print(f"{item['job_name']} | bad_rate={item['bad_rate']:.1%} | rejected={item['rejected']}/{item['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
