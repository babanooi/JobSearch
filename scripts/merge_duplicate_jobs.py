"""数据迁移：合并 job_skills 和 jd_documents 中的重复岗位名

用法：
  python scripts/merge_duplicate_jobs.py --dry-run   # 预览，不修改
  python scripts/merge_duplicate_jobs.py --execute    # 执行合并
"""
import sys
import os
import datetime
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from models.database import SessionLocal
from models.job import JobSkills
from models.document import JdDocument
from tools.skill_guard import normalize_job_name
from sqlalchemy import text


def merge_job_skills(dry_run: bool = True):
    """合并 job_skills 表"""
    with SessionLocal() as session:
        rows = session.query(JobSkills).all()

        # 按归一化名分组
        groups: dict[str, list[JobSkills]] = defaultdict(list)
        for row in rows:
            norm = normalize_job_name(row.job_name)
            groups[norm].append(row)

        merges = 0
        deletes = 0

        for norm_name, group in groups.items():
            if len(group) <= 1:
                continue

            print(f"\n[{norm_name}] 合并 {len(group)} 条记录:")
            for r in group:
                print(f"  - {r.job_name} | {r.skill_name} | count={r.count}")

            if dry_run:
                continue

            # 合并：同名 skill 合并 count + 最新 last_seen_at + 最大 total_jds
            merged: dict[str, JobSkills] = {}
            for r in group:
                if r.skill_name in merged:
                    existing = merged[r.skill_name]
                    existing.count += r.count
                    if r.last_seen_at and (not existing.last_seen_at or r.last_seen_at > existing.last_seen_at):
                        existing.last_seen_at = r.last_seen_at
                    existing.total_jds = max(existing.total_jds or 0, r.total_jds or 0)
                else:
                    r.job_name = norm_name
                    merged[r.skill_name] = r

            # 删除旧记录，插入合并后的
            old_ids = {r.id for r in group}
            for r in group:
                if r.id not in {m.id for m in merged.values()}:
                    session.delete(r)
                    deletes += 1

            session.flush()
            merges += len(group)

        if not dry_run:
            session.commit()
            print(f"\n迁移完成: 合并 {merges} 条 → 删除 {deletes} 条")
        else:
            print(f"\n[Dry-run] 将合并 {merges} 条记录")


def merge_jd_documents(dry_run: bool = True):
    """合并 jd_documents 表"""
    with SessionLocal() as session:
        rows = session.execute(
            text("SELECT id, job_name FROM jd_documents")
        ).fetchall()

        updates = 0
        for row in rows:
            norm = normalize_job_name(row[1])
            if norm != row[1]:
                print(f"  jd_documents: {row[1]} → {norm}")
                if not dry_run:
                    session.execute(
                        text("UPDATE jd_documents SET job_name = :new WHERE id = :id"),
                        {"new": norm, "id": row[0]},
                    )
                    updates += 1

        if not dry_run:
            session.commit()
            print(f"\njd_documents 迁移: {updates} 条")
        elif updates == 0:
            print("  jd_documents 无需迁移")


def show_final_state():
    """展示迁移后的 job_name 分布"""
    with SessionLocal() as session:
        rows = session.execute(
            text("SELECT job_name, COUNT(*) as cnt FROM job_skills GROUP BY job_name ORDER BY cnt DESC")
        ).fetchall()
        print("\n=== job_skills 岗位分布 ===")
        for r in rows:
            print(f"  {r[1]:4d} | {r[0]}")


if __name__ == "__main__":
    dry_run = "--execute" not in sys.argv
    if dry_run:
        print("=== Dry-run 模式（加 --execute 执行） ===\n")

    merge_jd_documents(dry_run=dry_run)
    merge_job_skills(dry_run=dry_run)
    show_final_state()
