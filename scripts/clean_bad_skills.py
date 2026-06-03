"""离线清洗 job_skills 表中的坏技能数据。

用法：
  python scripts/clean_bad_skills.py --dry-run
  python scripts/clean_bad_skills.py --execute
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from models.database import SessionLocal
from models.job import JobSkills
from tools.skill_guard import guard_skill_list


def clean(dry_run: bool = True):
    with SessionLocal() as session:
        rows = session.query(JobSkills).all()
        bad = []

        for row in rows:
            filtered = guard_skill_list([row.skill_name])
            if not filtered:
                bad.append(row)

        if not bad:
            print("未发现坏数据")
            return

        print(f"发现 {len(bad)} 条坏数据（共 {len(rows)} 条）:\n")
        for r in bad:
            print(f"  [{r.job_name}] {r.skill_name} (count={r.count})")

        if dry_run:
            print(f"\n[Dry-run] 将删除 {len(bad)} 条记录")
            return

        for r in bad:
            session.delete(r)
        session.commit()
        print(f"\n已删除 {len(bad)} 条记录")


if __name__ == "__main__":
    dry_run = "--execute" not in sys.argv
    if dry_run:
        print("=== Dry-run 模式（加 --execute 执行） ===\n")
    clean(dry_run=dry_run)
