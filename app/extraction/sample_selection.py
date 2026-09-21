"""20 样本选样与冻结（任务1 第一步）。

原则（B 任务书 + progress/week1/B/PROGRESS.md 登记）：
1. 固定 5 篇中的海报素材必选（3 张 poster 帖 + 1 张 mixed 帖内嵌海报）——它们是
   纵向演示主链，且 bundle 里有真实 SHA-256 可直接冻结；
2. 其余从 100 篇台账的 67 张海报中按标题关键词确定性打分（经验分享/选调/基层优先），
   得分相同按 notice_id 升序，保证可复现、无人工挑选空间；
3. 输出 data/gold/sample_selection_20.json：ID 集合立即冻结；
   image_sha256 在图片受控交接并核对后回填（哈希是图片的确定属性，
   回填不改变样本集合）。

用法：python -m app.extraction.sample_selection
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "evidence" / "week1" / "A" / "ledger" / "article_ledger.json"
FIXED_BUNDLES = ROOT / "evidence" / "week1" / "A" / "fixed_samples"
OUT = ROOT / "data" / "gold" / "sample_selection_20.json"

# 标题关键词得分：经验分享类优先（台账里 19 篇含经验分享关键词）
KEYWORDS = (
    ("选调", 3), ("经验", 3), ("分享", 2), ("基层", 2),
    ("公务员", 2), ("招录", 1), ("考取", 1), ("上岸", 1),
)

# 公告类标题标记（预告/讲座/模拟考试等）：不含人物五字段信息的概率较高，
# 仅作信息标记，不参与排除——没有图片时任何排除规则都是猜测，
# 简单确定规则 + 如实标注是最可辩护的选样方式。
ANNOUNCEMENT_RE = re.compile(r"预告|讲座|模拟|考试|答疑|培训|宣讲会|特训营|招聘活动")

# 固定样本中的海报素材（bundle 已在仓库，含真实 SHA-256）
FIXED_POSTER_ASSETS = ("247586", "247746", "247919", "348879")


def score_title(title: str) -> int:
    return sum(w for k, w in KEYWORDS if k in title)


def load_ledger() -> list[dict]:
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    return data["entries"]


def load_fixed_asset_hash(notice_id: str) -> str | None:
    bundle = FIXED_BUNDLES / f"{notice_id}.json"
    if not bundle.exists():
        return None
    data = json.loads(bundle.read_text(encoding="utf-8"))
    refs = [a for a in data.get("asset_refs", []) if a.get("kind") == "poster"]
    return refs[0]["sha256"] if refs else None


def _order(e: dict) -> tuple:
    return (-score_title(e["title"]), e["notice_id"])


def select(n: int = 20) -> dict:
    entries = load_ledger()
    posters = [e for e in entries
               if e.get("content_type") == "poster" and e.get("_source") == "real"
               and e.get("final_status") == "processed"]
    # 固定样本海报必选；剩余从候选池确定性打分补齐
    fixed = [e for e in posters if e["notice_id"] in FIXED_POSTER_ASSETS]
    pool = sorted(
        (e for e in posters if e["notice_id"] not in FIXED_POSTER_ASSETS),
        key=_order)
    chosen = fixed + pool[: n - len(fixed)]
    chosen.sort(key=lambda e: e["notice_id"])

    samples = []
    for i, e in enumerate(chosen, start=1):
        samples.append({
            "sample_id": f"P{i:02d}",
            "notice_id": e["notice_id"],
            "title": e["title"],
            "in_fixed_samples": e["notice_id"] in FIXED_POSTER_ASSETS,
            "is_announcement": bool(ANNOUNCEMENT_RE.search(e["title"])),
            "title_keyword_score": score_title(e["title"]),
            "image_sha256": load_fixed_asset_hash(e["notice_id"]),
            "annotated_by": None,
            "evidence_summary": None,
            "fields": {"cohort": None, "education": None, "major": None,
                       "city": None, "position_or_unit": None},
            "is_multi_person": None,
        })
    return {
        "sample_set": "week1-poster-gold-20",
        "frozen": True,
        "frozen_basis": "选样仅使用台账标题与固定样本清单（模型运行前冻结）；"
                        "image_sha256 由受控交接图片核对后回填",
        "selection_rule": "固定5篇海报素材必选 + 剩余按标题关键词得分降序、notice_id 升序；"
                          "is_announcement 仅标记公告类风险（稀疏金标准难例），不影响排序",
        "samples": samples,
    }


def main() -> int:
    selection = select()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(selection, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    hashed = sum(1 for s in selection["samples"] if s["image_sha256"])
    print(f"selection frozen: {len(selection['samples'])} samples "
          f"({hashed} with known sha256) -> {OUT.relative_to(ROOT)}")
    for s in selection["samples"]:
        mark = "*" if s["in_fixed_samples"] else " "
        print(f"  {s['sample_id']} {mark} {s['notice_id']} "
              f"score={s['title_keyword_score']} {s['title'][:38]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
