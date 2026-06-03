"""求职助手 CLI 入口"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.config import settings
from core.logger import get_logger

logger = get_logger("cli")


def cmd_serve():
    """启动 FastAPI 服务"""
    import uvicorn
    uvicorn.run("api.fastapi_app:app", host="0.0.0.0", port=8000, reload=True)


def cmd_ui():
    """启动 Streamlit Chat UI"""
    from streamlit.web import cli as stcli
    ui_path = str(Path(__file__).parent / "ui" / "streamlit_app.py")
    sys.argv = ["streamlit", "run", ui_path]
    stcli.main()


def cmd_analyze(job_name: str):
    """命令行直接分析岗位"""
    from graphs.analyze import agent_graph
    import uuid

    logger.info(f"分析岗位: {job_name}")
    result = agent_graph.invoke(
        {"job_name": job_name, "status": "开始执行"},
        config={"configurable": {"thread_id": str(uuid.uuid4())}},
    )
    print(f"状态: {result.get('status')}")
    print(f"技能数: {len(result.get('skill_list', []))}")
    print(f"收集 JD: {len(result.get('search_raw_items', []))} 条")


def cmd_rank(job_name: str, top_n: int = 10):
    """查询技能排名"""
    from agents.registry import registry
    skills = registry.db_tool.get_skill_rank(job_name, top_n)
    if not skills:
        print(f"未找到 {job_name} 的分析数据")
        return
    print(f"\n{job_name} 技能 Top{len(skills)}:")
    for i, s in enumerate(skills, 1):
        print(f"  {i}. {s['skill']} (出现 {s['count']} 次)")


def cmd_doctor():
    """环境自检"""
    checks = {
        "DeepSeek API": bool(settings.DEEPSEEK_API_KEY),
        "AnySearch API": bool(settings.ANYSEARCH_API_KEY),
        "Dashscope API": bool(settings.DASHSCOPE_API_KEY),
        "MySQL URL": bool(settings.DATABASE_URL),
    }
    for name, ok in checks.items():
        print(f"  {'OK' if ok else 'MISSING'} {name}")

    try:
        from models.database import get_engine
        get_engine().connect().close()
        print("  OK  MySQL 连接")
    except Exception as e:
        print(f"  FAIL MySQL 连接: {e}")

    try:
        from tools.embedding import create_embeddings
        emb = create_embeddings()
        emb.embed_query("test")
        print("  OK  Embedding API")
    except Exception as e:
        print(f"  FAIL Embedding: {e}")

    print("\n环境自检完成")


def main():
    parser = argparse.ArgumentParser(description="求职助手")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("serve", help="启动 FastAPI 服务")
    sub.add_parser("ui", help="启动 Streamlit Chat UI")
    sub.add_parser("doctor", help="环境自检")

    p_analyze = sub.add_parser("analyze", help="命令行分析岗位")
    p_analyze.add_argument("job_name", help="岗位名称")

    p_rank = sub.add_parser("rank", help="查询技能排名")
    p_rank.add_argument("job_name", help="岗位名称")
    p_rank.add_argument("--top", type=int, default=10, help="返回 Top N")

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve()
    elif args.command == "ui":
        cmd_ui()
    elif args.command == "doctor":
        cmd_doctor()
    elif args.command == "analyze":
        cmd_analyze(args.job_name)
    elif args.command == "rank":
        cmd_rank(args.job_name, args.top)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
