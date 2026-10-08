# evolution 模块：自进化 RAG 第一层记录循环

## 目录结构

```
evolution/
├── config.yaml              # 第一层配置
├── schemas.py               # 数据模型（QueryCase / RetrievalResult / GenerationRecord）
├── retriever.py             # 包装现有病理检索链路
├── selector.py              # 检索结果选择器
├── generator.py             # 生成模型接口（mock / api）
├── case_store.py            # QueryCase JSON 存储管理
├── logger.py                # 第一层主入口：QueryLogger
├── requirements.txt         # 额外依赖
├── examples/
│   └── run_first_layer.py   # 示例脚本
└── data/
    ├── query_cases/         # 查询记录 JSON 档案
    ├── overlay_units/       # 第二阶段：PatchOverlay 单元
    └── judge_reports/       # 第二阶段：裁决报告
```

## 快速开始

### 1. 启动病理检索服务

```bash
cd /mnt/data_1/yds/自进化/pathology_retrieval
/usr/bin/python3 pathology_vector_db_server.py --host 127.0.0.1 --port 8765
```

### 2. 运行第一层记录示例

```bash
cd /mnt/data_1/yds/自进化
/usr/bin/python3 evolution/examples/run_first_layer.py
```

### 3. 查看生成的 case

```bash
ls -la evolution/data/query_cases/
cat evolution/data/query_cases/case_*.json
```

## 核心类说明

### QueryLogger

第一层主入口。一次 `log()` 调用完成：

1. 调用现有检索链路，召回 top30；
2. 按配置选择最终喂给生成模型的文段；
3. 调用生成模型（当前为 mock）；
4. 组装 QueryCase 并保存为 JSON。

```python
from evolution.logger import QueryLogger

logger = QueryLogger.from_config("evolution/config.yaml")
case = logger.log("宫颈癌的病理诊断要点是什么？")
print(case.case_id)
```

### BaseRetriever

统一封装现有病理向量库调用：

- `mode: server`：调用常驻 HTTP 服务（推荐）。
- `mode: local`：本地直连 Milvus Lite（无需启动服务，但慢）。

### CaseStore

管理 `data/query_cases/` 目录下的 JSON 文件：

- `save(case)`: 保存
- `load(case_id)`: 加载
- `list_cases()`: 列出所有 case
- `update(case_id, updates)`: 更新字段

## 配置项

见 `config.yaml`，主要项：

| 配置 | 说明 |
|---|---|
| `retrieval.mode` | `server` 或 `local` |
| `retrieval.server_url` | 常驻服务地址 |
| `retrieval.record_topk` | 记录时召回数量（建议 30，用于混淆分析） |
| `retrieval.select_topk` | 最终选中文段数量 |
| `selection.strategy` | `topk` 或 `threshold` |
| `generation.mode` | `mock` 或 `api`（api 未实现） |
| `logging.auto_save` | 是否自动保存所有查询 |

## 下一步

第一层完成后，将进入第二层：**混淆分析 + 改造策略 + PatchOverlay**。
