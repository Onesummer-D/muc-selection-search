"""9/22 烟测回归：固定 5 篇 bundle 导入 C SQLite（Schema/行数/幂等）。

业务实现见 app/extraction/import_smoke.py；本测试保证其长期可重复，
供 9/22 交付与后续回归使用。
"""

from app.extraction.import_smoke import run


def test_fixed_five_import_smoke_schema_rows_and_idempotency():
    result = run(verbose=False)
    assert result["schema_ok"], "bundle Schema 预检失败"
    assert result["ok"], "烟测未通过"

    first, second = result["first_counts"], result["second_counts"]
    # 行数与 bundle 声明一致：5 文章 / 4 素材 / 7 人物 / 全部字段证据
    assert first["articles"] == 5
    assert first["assets"] == 4
    assert first["records"] == 7
    assert first["evidence"] == result["bundle_totals"]["evidence"]
    # evidence pack 与导入 evidence 交叉核对一致
    assert result["pack_evidence"] == first["evidence"]
    # 幂等：重复导入后业务四表行数不变；审计事件有意翻倍
    assert (first["articles"], first["assets"], first["records"],
            first["evidence"]) == (second["articles"], second["assets"],
                                   second["records"], second["evidence"])
    assert second["events"] == 2 * first["events"]
