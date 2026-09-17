"""受控资产落地：下载样本图片到仓库外目录并计算 SHA-256。

用途（A2 固定样本收尾）：
    python -m app.sync.finalize_assets --pool ../candidates_pool.json \
        --out ../controlled_assets

- 原图下载到 --out/<notice_id>/<asset_id>.jpg（仓库外，交接 B 时走受控渠道）；
- 逐图计算 SHA-256 并回写候选池 images[*]["sha256"]；
- 之后重跑 collect_fixed --from-pool 即可产出带真实摘要的 bundle。

仅下载公开可匿名访问的图片资源（门户 upload 目录），不触碰登录态。
"""
from __future__ import annotations

import argparse
import json
import time

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/126.0 Safari/537.36")


def _httpsify(url: str) -> str:
    """门户 upload 资源的 http:80 形式统一转为 https。"""
    return url.replace("http://my.muc.edu.cn:80/", "https://my.muc.edu.cn/")


def download_assets(pool_path: str, out_dir: str, only_ids: set | None = None,
                    sleep_seconds: float = 1.0) -> dict:
    """下载候选池内（或指定 notice_id 的）图片，回写 sha256。

    返回统计信息。失败图片保留占位摘要并在返回值中列出。
    """
    with open(pool_path, encoding="utf-8") as fh:
        pool = json.load(fh)

    session = requests.Session()
    session.headers["User-Agent"] = UA
    stats = {"downloaded": 0, "failed": [], "skipped_existing": 0}
    for article in pool:
        if only_ids is not None and article["notice_id"] not in only_ids:
            continue
        for idx, image in enumerate(article.get("images") or [], start=1):
            if not isinstance(image, dict) or not image.get("url"):
                continue
            asset_id = f"{article['notice_id']}-poster-{idx:02d}"
            if image.get("sha256"):
                stats["skipped_existing"] += 1
                continue
            url = _httpsify(image["url"])
            try:
                resp = session.get(url, timeout=20)
                resp.raise_for_status()
                data = resp.content
                if len(data) < 100 or not data[:2] == b"\xff\xd8":
                    # 非 JPEG（可能是被重定向的登录页）：保留占位并记录
                    stats["failed"].append({"asset_id": asset_id, "url": url,
                                            "reason": f"非图片响应({len(data)}B)"})
                    continue
            except requests.RequestException as exc:
                stats["failed"].append({"asset_id": asset_id, "url": url,
                                        "reason": str(exc)[:120]})
                continue
            import hashlib
            import os
            article_dir = f"{out_dir}/{article['notice_id']}"
            os.makedirs(article_dir, exist_ok=True)
            path = f"{article_dir}/{asset_id}.jpg"
            with open(path, "wb") as fh:
                fh.write(data)
            image["sha256"] = hashlib.sha256(data).hexdigest()
            stats["downloaded"] += 1
            print(f"[asset] {asset_id} <- {len(data)}B sha256={image['sha256'][:16]}…")
            time.sleep(sleep_seconds)

    with open(pool_path, "w", encoding="utf-8") as fh:
        json.dump(pool, fh, ensure_ascii=False, indent=1)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="受控资产落地与摘要计算")
    parser.add_argument("--pool", default="../candidates_pool.json")
    parser.add_argument("--out", default="../controlled_assets")
    parser.add_argument("--ids", default=None,
                        help="仅处理这些 notice_id（逗号分隔）；默认全部")
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args()

    only_ids = (set(args.ids.split(",")) if args.ids else None)
    stats = download_assets(args.pool, args.out, only_ids, args.sleep)
    print(f"[done] 下载 {stats['downloaded']}，已有摘要跳过 {stats['skipped_existing']}，"
          f"失败 {len(stats['failed'])}")
    for f in stats["failed"]:
        print(f"[fail] {f['asset_id']}: {f['reason']}")
    print(f"[note] 原图目录（仓库外，交接 B）：{args.out}")
    return 0 if not stats["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
