"""第一层记录循环示例：记录一次查询并打印结果。"""

from __future__ import annotations

import sys
from pathlib import Path

# 将项目根目录加入路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from evolution.logger import QueryLogger
from evolution.schemas import CaseLabel


def main():
    # 从 evolution/config.yaml 加载配置
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    logger = QueryLogger.from_config(config_path)

    # 示例查询
    query = "宫颈癌的病理诊断要点是什么？"

    # 记录完整链路
    case = logger.log(
        query=query,
        label=CaseLabel.AUTO,
        tags=["示例", "第一层"],
        notes="这是第一层记录循环的示例 case。",
    )

    print("\n--- Case 摘要 ---")
    print(f"case_id: {case.case_id}")
    print(f"query: {case.query}")
    print(f"retrieval top30 count: {len(case.retrieval.get('results', []))}")
    print(f"selected chunks: {case.selected_chunks}")

    # 演示人工打标签
    labeled = logger.label_case(
        case_id=case.case_id,
        label=CaseLabel.PENDING,
        tags=["待分析", "排序问题"],
        notes="研究者认为关键文段排名靠后，需要进一步分析。",
        is_satisfactory=False,
    )
    print(f"\n已更新标签: {labeled.label.value}")
    print(f"当前 case 列表: {logger.list_cases()}")


if __name__ == "__main__":
    main()
