"""切片6测试：多模态适配器——补任务书场景5的「模型超时」缺口。

注入假 client 覆盖解析、词典校验、超时与失败状态；被测的是适配器逻辑，
不 mock 被测抽取器本身。
"""

import json

import pytest

from app.extraction import Extractor, validate_bundle
from app.extraction.multimodal import MultimodalAdapter, MultimodalTimeout

from tests.extraction.test_poster_rules import _article


@pytest.fixture
def asset_env(tmp_path, monkeypatch):
    """受控资产目录：造一张占位图，让 resolve_asset_path 找得到文件。

    假 client 不会真的读图，文件内容无关紧要。
    """
    asset_dir = tmp_path / "controlled"
    poster = asset_dir / "247919" / "poster-01.jpg"
    poster.parent.mkdir(parents=True)
    poster.write_bytes(b"\xff\xd8fake")
    monkeypatch.setenv("EXTRACTION_ASSET_DIR", str(asset_dir))
    return asset_dir


def _ok_response():
    return json.dumps({"records": [{
        "cohort": "2025届", "grade": None, "education": "本科",
        "college": None, "major": "计算机科学与技术", "city": "成都",
        "position_or_unit": "某区基层岗位",
        "evidence": [
            {"field": "city", "text": "工作地点 成都"},
            {"field": "education", "text": "本科"},
            {"field": "cohort", "text": "2025届"},
            {"field": "major", "text": "计算机科学与技术"},
            {"field": "position_or_unit", "text": "某区基层岗位"},
        ]}]}, ensure_ascii=False)


def _asset_refs():
    return [{"asset_id": "247919-poster-01", "kind": "poster",
             "local_ref": "private://247919/poster-01", "sha256": "a" * 64}]


def test_multimodal_valid_output_produces_bundle_records(asset_env):
    adapter = MultimodalAdapter(client=lambda p, img: _ok_response())
    bundle = Extractor(ocr_adapter=adapter).extract(
        _article(content_type="poster", asset_refs=_asset_refs()))
    assert validate_bundle(bundle) == [], validate_bundle(bundle)
    rec = bundle["records"][0]
    assert rec["education"] == "本科" and rec["city"] == "成都"
    assert rec["review_status"] == "processed"
    methods = {e["method"] for e in rec["evidence"]}
    assert methods == {"multimodal"}
    assert all(e["asset_id"] == "247919-poster-01" for e in rec["evidence"])


def test_model_timeout_produces_failed_status(asset_env):
    """任务书场景5：模型超时必须产生状态和失败原因。"""
    def slow_client(prompt, image):
        raise MultimodalTimeout("inference exceeded 30s")
    adapter = MultimodalAdapter(client=slow_client)
    bundle = Extractor(ocr_adapter=adapter).extract(
        _article(content_type="poster", asset_refs=_asset_refs()))
    assert bundle["processing_status"] == "failed"
    assert bundle["failure_reason"] == "model_timeout"
    assert bundle["records"] == []


def test_model_generic_error_produces_reason(asset_env):
    def broken_client(prompt, image):
        raise RuntimeError("HTTP 502")
    adapter = MultimodalAdapter(client=broken_client)
    bundle = Extractor(ocr_adapter=adapter).extract(
        _article(content_type="poster", asset_refs=_asset_refs()))
    assert bundle["processing_status"] == "failed"
    assert bundle["failure_reason"] == "model_error:RuntimeError"


def test_invalid_json_produces_reason_not_garbage(asset_env):
    adapter = MultimodalAdapter(client=lambda p, img: "抱歉，我无法识别这张图片")
    bundle = Extractor(ocr_adapter=adapter).extract(
        _article(content_type="poster", asset_refs=_asset_refs()))
    assert bundle["processing_status"] == "failed"
    assert bundle["failure_reason"] == "model_invalid_json"


def test_fenced_json_is_parsed(asset_env):
    raw = "```json\n" + _ok_response() + "\n```"
    adapter = MultimodalAdapter(client=lambda p, img: raw)
    bundle = Extractor(ocr_adapter=adapter).extract(
        _article(content_type="poster", asset_refs=_asset_refs()))
    assert bundle["records"] and bundle["records"][0]["city"] == "成都"


def test_dictionary_violation_flags_review_not_silent(asset_env):
    """学历不在枚举 → 词典校验失败 → review_required，值保留供人工复核。"""
    bad = json.dumps({"records": [{
        "cohort": "2025届", "grade": None, "education": "大专",
        "college": None, "major": None, "city": "成都",
        "position_or_unit": None,
        "evidence": [{"field": "city", "text": "工作地点 成都"}]}]},
        ensure_ascii=False)
    adapter = MultimodalAdapter(client=lambda p, img: bad)
    bundle = Extractor(ocr_adapter=adapter).extract(
        _article(content_type="poster", asset_refs=_asset_refs()))
    rec = bundle["records"][0]
    assert rec["review_status"] == "review_required"
    assert bundle["failure_reason"] == "dictionary_violation"


def test_field_without_evidence_flags_review(asset_env):
    """有值无证据的字段必须进复核（接口字典：无证据不得进入回答上下文）。"""
    no_ev = json.dumps({"records": [{
        "cohort": "2025届", "grade": None, "education": "本科",
        "college": None, "major": "软件工程", "city": None,
        "position_or_unit": None,
        "evidence": [{"field": "cohort", "text": "2025届"}]}]},  # major 无证据
        ensure_ascii=False)
    adapter = MultimodalAdapter(client=lambda p, img: no_ev)
    bundle = Extractor(ocr_adapter=adapter).extract(
        _article(content_type="poster", asset_refs=_asset_refs()))
    rec = bundle["records"][0]
    assert rec["major"] == "软件工程"  # 值保留
    assert rec["review_status"] == "review_required"  # 但进复核


def test_missing_fields_stay_null_and_bundle_valid(asset_env):
    partial = json.dumps({"records": [{
        "cohort": None, "grade": None, "education": None, "college": None,
        "major": None, "city": "成都", "position_or_unit": None,
        "evidence": [{"field": "city", "text": "工作地点 成都"}]}]},
        ensure_ascii=False)
    adapter = MultimodalAdapter(client=lambda p, img: partial)
    bundle = Extractor(ocr_adapter=adapter).extract(
        _article(content_type="poster", asset_refs=_asset_refs()))
    assert validate_bundle(bundle) == []
    rec = bundle["records"][0]
    assert rec["cohort"] is None and rec["education"] is None
    assert rec["review_status"] == "review_required"


# ---- 真实客户端配置校验（不发网络请求）----

def test_real_client_requires_api_key(asset_env, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        MultimodalAdapter()


def test_real_client_requires_model(asset_env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        MultimodalAdapter()


def test_real_client_constructs_with_config(asset_env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-vlm")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    adapter = MultimodalAdapter()
    assert callable(adapter._client)
    assert adapter.model == "test-vlm"
    assert adapter.base_url == "https://example.invalid/v1"
    assert "test-key" not in str(adapter.__dict__)  # Key 不落对象属性
