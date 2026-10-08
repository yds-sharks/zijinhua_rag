# 自进化 RAG 框架设计说明书

## 1. 项目定位

本项目是一个**面向医学病理领域的自进化检索增强生成（RAG）框架**。它在现有 178 万规模病理向量库（BaseIndex）之上，增加三层进化循环：

1. **记录循环**：完整记录每一次查询的检索与生成链路，沉淀 case。
2. **本地优化循环**：基于混淆分析改造已有文段的表达，生成 PatchOverlay，提升检索效果。
3. **外部知识注入循环**：当库中完全没有答案时，接收 PDF/URL/文本，提取新知识并入库。

当前阶段（第一阶段）聚焦实现**第一层 + 第二层的最小闭环**。第三层复用之前《外部知识注入通道》的设计，后续再接入。

---

## 2. 核心设计思想

### 2.1 不替换主库，只增加"补丁层"

原始 178 万向量库（BaseIndex）是稳定底座，**只读、不覆盖、不重写**。

所有优化产物（改写后的文段、新增知识）进入独立的 **PatchOverlay（小子库/额外索引）**。

检索时，PatchOverlay 与 BaseIndex 共同参与召回，但地位不同：

- BaseIndex：提供原始证据。
- PatchOverlay：提供"更好的检索表达"，帮助把 BaseIndex 中原本排得靠后的正确文段顶上来。

### 2.2 问题驱动，而非数据驱动

进化的触发条件是**真实查询失败**，而不是定期全量重跑。

系统只负责：

- 记录失败 case；
- 提供分析工具；
- 执行经过裁决的改写。

研究者负责：

- 判断哪些 case 需要优化；
- 触发改造流程；
- 验收裁决结果。

### 2.3 改写必须可审计、可回滚

每条 PatchOverlay 记录都必须能追溯到：

- 原始文段 ID / 来源；
- 触发改写的查询 case；
- 采用的改造策略；
- 改写前后的文本；
- 裁决结果（通过 / 拒绝 / 待观察）。

任何改写都可以被单独停用或删除，不影响 BaseIndex。

### 2.4 全局安全优先于单点优化

单条查询的优化很容易，但可能污染其他查询。因此所有改写必须经过**自动外部裁决**：

- 目标查询的检索效果是否提升；
- 全局测试集是否出现性能回退；
- 是否引入与现有知识的冲突。

通过后才能进入 PatchOverlay。

---

## 3. 三层循环架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         第一层：记录循环                          │
│  记录：query → top-k 检索结果 → 选中片段 → 生成输出 → 标签        │
│  产物：QueryCase（JSON 档案）                                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    研究者挑选失败 case
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         第二层：本地优化循环                      │
│  1. 混淆分析：对 top30 逐条分类                                   │
│  2. 策略模型：判断改造类型（SPLIT / CONTEXTUALIZE /              │
│              ANCHOR / RETIRE）                                  │
│  3. 改写模型：执行具体改造                                        │
│  4. 外部裁决：验证目标查询提升 + 全局无回退                       │
│  产物：PatchOverlay 单元                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
              PatchOverlay 作为"查询扩展索引"参与召回
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         第三层：外部知识注入循环                  │
│  触发：库里完全没有相关文段                                       │
│  输入：PDF / URL / 文本片段                                       │
│  处理：解析 → 清洗 → 拆段 → 质量检查 → 写入 PatchOverlay         │
│  产物：新增 KnowledgeUnit                                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 关键概念

### 4.1 BaseIndex

现有病理向量库，约 178 万条向量，基于 BM25 + BGE-M3 稠密向量混合检索。在本项目中作为**只读底座**。

### 4.2 PatchOverlay

一个独立的轻量索引层，存储两类内容：

- **改写型单元**：对 BaseIndex 已有文段的优化表达。
- **新增知识单元**：外部注入的新知识（第三阶段实现）。

PatchOverlay 不替换 BaseIndex 原文，而是作为**额外检索表达**存在。查询时，PatchOverlay 被用来扩展查询语义，再去 BaseIndex 中召回真正原始文段。

### 4.3 QueryCase

一次完整查询记录的档案，包含：

- 原始查询
- 检索 top-k 结果
- 最终选中文段
- 生成模型输出
- 人工/自动标签（成功 / 失败 / 待分析）
- 关联的 PatchOverlay 单元 ID

### 4.4 混淆分析

针对某条失败查询，分析其 top30 检索结果中每个文段与"用户真实意图"的关系，划分为四类：

| 类别 | 含义 | 后续动作 |
|---|---|---|
| 命中且靠前 | 检索正确，排序也正确 | 无需处理 |
| 命中但靠后 | 文段相关，但被其他文段压住 | 考虑 ANCHOR / CONTEXTUALIZE |
| 误排靠前 | 文段不相关，却排在前面 | 考虑 RETIRE / SPLIT |
| 误排靠后 | 文段不相关，且正确被淘汰 | 无需处理 |

### 4.5 改造策略

由策略模型判断文段需要哪种改造。当前定义四种：

| 策略 | 含义 | 典型场景 |
|---|---|---|
| **SPLIT** | 拆分主题混杂 | 一段里讲了多个主题，需要拆开 |
| **CONTEXTUALIZE** | 补全疾病主体 | 原文省略主语或场景，检索时匹配不上 |
| **ANCHOR** | 增加诊断锚点 | 缺少关键术语、别名、检查方法 |
| **RETIRE** | 抑制重复竞争 | 多段重复内容互相抢排名 |

---

## 5. 数据流与模块划分

```
用户查询
    │
    ▼
┌──────────────────┐
│  QueryLogger     │  第一层：记录完整查询链路
│  （记录模块）      │
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  BaseRetriever   │  调用现有病理检索链路
│  （复用 pathology_retrieval）│
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  ResultSelector  │  选择最终喂给生成模型的文段
│  （可简单取 top-k 或 rerank）│
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  Generator       │  生成模型，产生最终回答
│  （可 mock / 可接真实模型）   │
└──────────────────┘
    │
    ▼
失败 case 被研究者选中
    │
    ▼
┌──────────────────┐
│  ConfusionAnalyzer│ 第二层：对 top30 逐条分类
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  StrategyModel   │  判断改造策略（API → 未来蒸馏小模型）
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  RewriteModel    │  执行具体改造
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  ExternalJudge   │  自动裁决：目标提升 + 全局无回退
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  PatchOverlay    │  写入额外索引
│  IndexManager    │
└──────────────────┘
```

---

## 6. 数据格式规范

所有持久化数据使用 JSON。主要数据对象定义如下。

### 6.1 QueryCase（查询记录）

```json
{
  "case_id": "case_20260918_001",
  "query": "宫颈癌的病理诊断要点是什么？",
  "timestamp": "2026-09-18T10:30:00+08:00",
  "retrieval": {
    "topk": 30,
    "results": [
      {
        "rank": 1,
        "pk": 460316045491836000,
        "score": 0.532,
        "dense": 0.0,
        "sparse": 1.33,
        "file_name": "新插入文件.json",
        "text": "宫颈癌的病理类型绝大部分为鳞癌。",
        "is_relevant": true,
        "confusion_category": "hit_top"
      }
    ]
  },
  "selected_chunks": [460316045491836000],
  "generation": {
    "model": "qwen2.5-72b",
    "output": "宫颈癌的病理诊断要点包括...",
    "has_hallucination": false,
    "is_satisfactory": false
  },
  "label": "failed",
  "tags": ["排序错误", "关键文段靠后"],
  "related_overlay_ids": []
}
```

### 6.2 OverlayUnit（PatchOverlay 单元）

```json
{
  "overlay_id": "ovl_20260918_001",
  "overlay_type": "rewrite",
  "source_pk": 460316045491836000,
  "source_file_name": "新插入文件.json",
  "source_text": "宫颈癌的病理类型绝大部分为鳞癌。",
  "trigger_case_id": "case_20260918_001",
  "strategy": "ANCHOR",
  "strategy_reason": "缺少诊断锚点术语",
  "rewritten_text": "宫颈癌（cervical cancer）的病理类型绝大部分为鳞状细胞癌（squamous cell carcinoma），病理诊断需结合活检与 HPV 检测。",
  "status": "accepted",
  "judge_result": {
    "target_query_improved": true,
    "global_regression": false,
    "conflict_detected": false,
    "passed_at": "2026-09-18T10:35:00+08:00"
  },
  "created_at": "2026-09-18T10:32:00+08:00"
}
```

### 6.3 JudgeReport（裁决报告）

```json
{
  "judge_id": "judge_20260918_001",
  "overlay_id": "ovl_20260918_001",
  "target_case_id": "case_20260918_001",
  "target_query": "宫颈癌的病理诊断要点是什么？",
  "metrics_before": {
    "recall@5": 0.2,
    "mrr": 0.125,
    "target_chunk_rank": 12
  },
  "metrics_after": {
    "recall@5": 0.8,
    "mrr": 0.5,
    "target_chunk_rank": 2
  },
  "global_test_set": {
    "num_queries": 100,
    "recall@5_delta": 0.0,
    "mrr_delta": -0.01,
    "regression_detected": false
  },
  "passed": true,
  "timestamp": "2026-09-18T10:35:00+08:00"
}
```

---

## 7. PatchOverlay 的召回机制

采用 **"查询扩展"** 策略（3.3C）：

1. 用户输入查询 Q。
2. 先在 PatchOverlay 中检索，得到一组"优化表达"单元。
3. 将这些单元的 rewritten_text 与原始查询 Q 融合，形成扩展查询 Q'。
4. 用 Q' 在 BaseIndex 中检索，得到最终候选文段。
5. 返回的仍是 BaseIndex 中的原始文段（含原始 file_name / text），保证证据可追溯。

**为什么不用两路召回后 rerank？**

因为 PatchOverlay 里存的是"检索表达"，不是替代证据。最终展示给用户的必须是 BaseIndex 原始文段，避免模型改写后的文本被当作原始证据。

---

## 8. 自动裁决机制

每条改写进入 PatchOverlay 前，必须完成自动裁决：

### 8.1 目标查询验证

- 使用改写前/后的 PatchOverlay，分别对触发该改写的目标查询做检索。
- 计算指标：Recall@k、MRR、目标文段排名。
- 必须满足：目标文段排名提升，或 Recall@k / MRR 提升。

### 8.2 全局回归测试

- 准备一组全局测试查询（可复用历史成功 case）。
- 对比改写前后整体指标变化。
- 若出现显著回退（如 Recall@5 下降超过阈值），拒绝该改写。

### 8.3 冲突检测

- 检查改写后的文本是否与现有 accepted OverlayUnit 高相似但结论相反。
- 若存在冲突，标记为 pending，不自动入库，等待人工复核。

### 8.4 通过标准

```
passed = target_improved AND NOT global_regression AND NOT conflict_detected
```

---

## 9. 策略模型与改写模型

### 9.1 第一阶段：API 驱动

初期不训练小模型，直接调用大模型 API：

- **StrategyModel**：输入"查询 + 文段 + 混淆类别"，输出改造策略（SPLIT / CONTEXTUALIZE / ANCHOR / RETIRE）及理由。
- **RewriteModel**：输入"策略 + 原始文段 + 查询"，输出改写后的文本。

### 9.2 第二阶段：蒸馏小模型

积累足够多标注数据后，从 API 输出中蒸馏一个小模型：

- 输入：文段文本 + 查询 + 简单特征（长度、实体数、主题集中度）。
- 输出：改造策略概率分布。
- 可选基础模型：BERT-base-Chinese、Qwen2.5-0.5B/1.5B、MacBERT 等。

蒸馏条件：

- 至少积累 N 条高质量标注（N 建议 500~2000，视类别平衡而定）。
- API 与小模型在验证集上达到可接受一致性（如 F1 > 0.8）。

---

## 10. 实施路线图

### 第一阶段：记录 + 本地优化最小闭环

目标：跑通一个失败 case 从记录到 PatchOverlay 的全流程。

| 步骤 | 任务 | 产出 |
|---|---|---|
| 1 | 实现 QueryLogger，记录一次查询的完整链路 | query_cases/ 目录 + JSON 档案 |
| 2 | 实现 ConfusionAnalyzer，支持 top30 分类 | 标注工具 / 自动初标 |
| 3 | 实现 StrategyModel（API 版） | 策略判断接口 |
| 4 | 实现 RewriteModel（API 版） | 四类改写接口 |
| 5 | 实现 PatchOverlay IndexManager（JSON/轻量向量） | overlay_units/ 目录 |
| 6 | 实现 ExternalJudge 自动裁决 | judge_reports/ 目录 |
| 7 | 改造 BaseRetriever，支持 PatchOverlay 查询扩展 | 联合召回接口 |
| 8 | 端到端跑通一个真实失败 case | 可演示的闭环 |

### 第二阶段：蒸馏小模型 + 批量优化

- 积累 case 数据。
- 训练 StrategyModel 小模型。
- 支持批量 case 自动分析。
- 优化裁决效率（避免每条改写都跑全量全局测试）。

### 第三阶段：外部知识注入

- 接入 PDF / URL / 文本解析。
- 实现 KnowledgeUnit 提取与质量检查。
- 与 PatchOverlay 合并写入流程。

---

## 11. 与现有病理检索链路的关系

现有 `pathology_retrieval/` 目录提供：

- `pathology_vector_db_server.py`：常驻检索服务。
- `call_pathology_vector_db.py`：本地/远程调用接口。
- `insert/config.yaml` + `bm25_bge_vectorstore_v2`：检索核心。

本项目中的 `BaseRetriever` 直接复用上述能力，不修改其内部实现。PatchOverlay 和进化模块作为独立目录 `evolution/` 开发。

---

## 12. 附录：术语表

| 术语 | 含义 |
|---|---|
| BaseIndex | 原始 178 万病理向量库，只读 |
| PatchOverlay | 额外索引层，存改写表达和新增知识 |
| QueryCase | 一次查询的完整记录档案 |
| OverlayUnit | PatchOverlay 中的单个单元 |
| Confusion Category | top30 中文段的四类定位（命中靠前/命中靠后/误排靠前/误排靠后） |
| Strategy | 改造策略：SPLIT / CONTEXTUALIZE / ANCHOR / RETIRE |
| External Judge | 自动裁决模块，验证改写安全性 |
| Query Expansion | 用 PatchOverlay 扩展查询语义，再去 BaseIndex 召回 |

---

## 13. 当前阶段目标

**先不急着写代码**。下一步：

1. 你确认这份 README 是否准确反映你的设计意图。
2. 若有偏差，在这一步修正。
3. 确认无误后，再按"第一阶段"任务清单开始实现。

请 review 后指出要调整的地方。
