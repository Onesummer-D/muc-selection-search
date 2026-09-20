"""多模态 API 脱敏烟测（任务 0 / B_goal「验证多模态API可做一次脱敏烟测」）。

素材：程序合成的测试海报（PIL 绘制，内容为虚构数据，无任何真实个人信息），
符合任务书「未经确认不得上传原始个人海报，只能使用已脱敏且获准的内部评测素材」。

流程：加载本地 .env → 合成海报 → MultimodalAdapter 真实客户端调用 →
JSON 解析 + 字段词典 + extraction_bundle.v1 Schema 校验 → 结果写
evidence/week1/B/multimodal-smoke.json。

用法：python -m app.extraction.smoke_multimodal
退出码 0 = 烟测通过（产出结构合法且过 Schema 的记录）。
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"
EVIDENCE = ROOT / "evidence" / "week1" / "B" / "multimodal-smoke.json"


def load_env() -> None:
    """极简 .env 加载：KEY=VALUE，# 注释；不覆盖已存在的环境变量。"""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and value and key not in os.environ:
            os.environ[key] = value


def make_synthetic_poster(out_path: Path) -> None:
    """合成脱敏测试海报：虚构人物字段，无真实姓名/照片/个人数据。"""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 42)
    small = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 26)
    img = Image.new("RGB", (900, 1100), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 899, 120], fill=(30, 64, 132))
    draw.text((40, 35), "选调经验分享（合成测试海报）", font=font, fill="white")
    lines = [
        "姓名：测试同学",
        "2025届  本科",
        "专业：软件工程",
        "信息学院",
        "工作地点：成都",
        "录用为成都市某区基层岗位",
    ]
    y = 180
    for line in lines:
        draw.text((60, y), line, font=font, fill="black")
        y += 110
    draw.text((60, 1020), "SYNTHETIC MATERIAL - NO REAL PII",
              font=small, fill=(120, 120, 120))
    img.save(out_path)


def run() -> int:
    from .multimodal import MultimodalAdapter
    from .bundle import validate_bundle
    from .extractor import Extractor

    load_env()
    if not os.environ.get("LLM_API_KEY"):
        print("[smoke] .env 中未配置 LLM_API_KEY，烟测未执行", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        asset_dir = tmp_path / "controlled"
        poster = asset_dir / "smoke-001" / "poster-01.png"
        poster.parent.mkdir(parents=True)
        make_synthetic_poster(poster)
        os.environ["EXTRACTION_ASSET_DIR"] = str(asset_dir)

        article = {
            "schema_version": "article_bundle.v1",
            "notice_id": "smoke-001",
            "title": "合成脱敏烟测海报",
            "source_url": "https://example.invalid/smoke-001",
            "published_at": "2026-09-19T16:00:00+08:00",
            "content_type": "poster",
            "clean_text": None,
            "asset_refs": [{
                "asset_id": "smoke-001-poster-01", "kind": "poster",
                "local_ref": "private://smoke-001/poster-01",
                "sha256": __import__("hashlib").sha256(
                    poster.read_bytes()).hexdigest(),
            }],
            "fetch_status": "processed",
            "failure_reason": None,
            "fetched_at": "2026-09-19T16:00:00+08:00",
        }

        adapter = MultimodalAdapter()
        start = time.perf_counter()
        bundle = Extractor(ocr_adapter=adapter).extract(article)
        wall_s = round(time.perf_counter() - start, 2)
        errors = validate_bundle(bundle)

        result = {
            "ok": not errors and bool(bundle["records"]),
            "wall_seconds": wall_s,
            "adapter_elapsed_s": round(adapter.last_elapsed_s, 2),
            "failure_reason": bundle["failure_reason"],
            "processing_status": bundle["processing_status"],
            "records": bundle["records"],
            "schema_errors": errors,
            # 任务3 / 审查报告 P1-08 要求登记的数据处理边界
            "boundary": {
                "provider": adapter.provider or "未登记",
                "model": adapter.model or "未登记",
                "base_url": adapter.base_url,
                "material_type": "程序合成测试海报（虚构人物，无真实个人信息，无照片）",
                "authorization_basis": "软件工程课程内部评测，合成素材，非个人数据",
                "price_date": "待登记（首次正式对照评测时按服务商定价页记录）",
                "retention_policy": "烟测结果存 evidence/week1/B/；合成图用后即弃；不发送任何真实个人海报",
                "smoke_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
        }
        EVIDENCE.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(json.dumps({k: result[k] for k in
                          ("ok", "wall_seconds", "failure_reason",
                           "processing_status", "schema_errors")},
                         ensure_ascii=False, indent=2))
        if result["ok"]:
            rec = result["records"][0]
            print(f"[smoke] 通过：cohort={rec['cohort']} education={rec['education']} "
                  f"major={rec['major']} city={rec['city']} "
                  f"position={rec['position_or_unit']}")
            print(f"[smoke] 证据已写 {EVIDENCE.relative_to(ROOT)}")
            return 0
        print("[smoke] 未通过，详见证据文件", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
