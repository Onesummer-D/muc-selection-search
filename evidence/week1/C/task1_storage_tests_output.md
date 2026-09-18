# 任务1 契约与存储 证据（角色 C）

- 日期：2026-09-18（本地）
- 分支：feat/week1-core-search（基于 3c80170，已合并附录 G 决策变更）
- 环境：Windows，Python 3.13.15，SQLite runtime 3.50.4

## 交付内容

| 文件 | 职责 |
|---|---|
| `app/domain/models.py` | Article / Asset / ExperienceRecord / Evidence / ProcessingEvent 领域模型与契约常量；含 7 个私有字段（person_name、avatar_ref、qr_code_ref、contact_info、meeting_entry、original_asset_ref、source_sso_url） |
| `app/domain/validation.py` | article_bundle.v1 / extraction_bundle.v1 契约校验：必填键、枚举、ISO 8601、private:// 前缀、sha256、bbox 四元数组、failed 必带原因；校验先于任何写入 |
| `app/domain/errors.py` | ContractViolation / StorageIntegrityError / MissingArticleError |
| `app/repository/base.py` | Repository 抽象接口（业务层不绑定 sqlite3） |
| `app/repository/sqlite_repository.py` | SQLite 五表实现：articles（notice_id 唯一）、assets（asset_id 唯一）、experience_records（record_key 唯一，一帖多人）、evidence（关联 record_key+字段名）、processing_events；参数化语句 + 外键约束 + 幂等 upsert |
| `app/repository/importer.py` | BundleImporter：校验 → 事务内写入 → 记录事件；重复导入只更新不增行，visibility 与私有字段不被导入覆盖 |
| `tests/core/test_storage.py` | 12 个契约测试（含 19 个非法 bundle 子用例） |

## 命令与实际输出

```
$ python -m unittest discover -s tests/core -v
test_article_and_assets_persisted ... ok
test_deliberate_duplicate_article_import_no_row_growth ... ok
test_deliberate_duplicate_extraction_import_no_row_growth ... ok
test_evidence_relations ... ok
test_extraction_before_article_rejected ... ok
test_failed_article_bundle_stores_reason_and_event ... ok
test_failed_extraction_bundle_records_event_without_records ... ok
test_invalid_bundles_rejected_without_writes ... ok
test_multiple_records_per_notice ... ok
test_null_fields_stored_as_null ... ok
test_review_required_record_is_draft_and_hidden_from_published ... ok
test_valid_bundle_with_second_asset_updates_count ... ok

----------------------------------------------------------------------
Ran 12 tests in 0.011s

OK
```

## 任务书要求对照

| 任务书要求 | 对应测试 | 结果 |
|---|---|---|
| 五张表；notice_id 与 record_key 唯一；一帖多人 | test_article_and_assets_persisted、test_multiple_records_per_notice | 通过 |
| 导入重复 bundle 必须更新而不增行 | test_deliberate_duplicate_article_import_no_row_growth、test_deliberate_duplicate_extraction_import_no_row_growth | 通过 |
| 为 null 写测试 | test_null_fields_stored_as_null | 通过 |
| 为 review_required 写测试 | test_review_required_record_is_draft_and_hidden_from_published | 通过 |
| 为 failed 写测试 | test_failed_article_bundle_stores_reason_and_event、test_failed_extraction_bundle_records_event_without_records | 通过 |
| 为证据关系写测试 | test_evidence_relations | 通过 |
| 故意重复导入一次，证明总数不增加 | 两个 deliberate_duplicate 测试（实体行数前后相等；processing_events 是审计日志，有意随导入次数增长，已在测试中显式断言） | 通过 |

## 设计说明

- 幂等实现：SQLite `INSERT ... ON CONFLICT DO UPDATE`，冲突键为 notice_id / asset_id / record_key；证据按 record_key 整组替换，不追加。
- 导入不写 visibility（保持 draft/published/withdrawn 生命周期归人工复核），不写 7 个私有字段（无 bundle 来源）。
- extraction bundle 先于 article bundle 导入时，外键约束触发 MissingArticleError 并整体回滚（含事件），符合“先 A 后 B”的交接顺序。
- 契约校验与 ARCHITECTURE 第 9 节一致：业务层只依赖 Repository 接口。
