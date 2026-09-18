"""接口与素材可用性核查（A1）的探测工具。

用法（在仓库根目录）：
    python -m app.datasource.probe_endpoints --portal-base-url https://my.muc.edu.cn

流程：打开有界面浏览器 → 人工完成 ZFCA/CAS 登录 → 登录者在页面中
打开"就业信息"等目标栏目 → 本脚本捕获浏览器实际发出的 XHR/fetch 请求，
识别 JSON 接口（特别是 getNoticeByPage / getNotice 类），输出：
  1. 接口清单（方法、URL、请求参数、响应摘要）
  2. 推断的栏目 ID（columnId 等参数值）
结果写入 evidence/week1/A/endpoint-probe.json，供回填 .env 使用。

注意：本脚本只做只读观察，不发送任何请求；账号密码由人工在浏览器输入。
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone

INTEREST_PATTERNS = (
    "getNoticeByPage", "getNotice", "notice", "article", "list",
    "column", "channel", "content",
)


def _short(body: str, limit: int = 400) -> str:
    return body[:limit] + ("..." if len(body) > limit else "")


def main() -> int:
    parser = argparse.ArgumentParser(description="门户接口探测（A1 核查）")
    parser.add_argument("--portal-base-url", required=True)
    parser.add_argument("--out", default="evidence/week1/A/endpoint-probe.json")
    parser.add_argument("--wait-minutes", type=float, default=10.0,
                        help="登录+浏览的等待窗口（分钟），到时自动收尾")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("需要 playwright：pip install playwright "
                           "&& playwright install chromium") from exc

    captured: list[dict] = []
    column_ids: dict[str, int] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        def on_response(response):
            try:
                req = response.request
                url = response.url
                if any(pat.lower() in url.lower() for pat in INTEREST_PATTERNS):
                    method = req.method
                    post = req.post_data or ""
                    try:
                        body = response.text()
                    except Exception:  # noqa: BLE001 - 二进制等
                        body = ""
                    entry = {
                        "method": method,
                        "url": url,
                        "status": response.status,
                        "post_data": _short(post),
                        "response_head": _short(body),
                        "captured_at": datetime.now(timezone.utc).isoformat(),
                    }
                    captured.append(entry)
                    print(f"[capture] {method} {url} -> {response.status}")
                    # 从参数里挖栏目 ID 线索
                    for key in ("columnId", "column_id", "channelId", "categoryId"):
                        for source in (url, post):
                            m = re.search(rf"{key}[\"'=:\s]+([\w-]+)", source)
                            if m:
                                column_ids[m.group(1)] = column_ids.get(m.group(1), 0) + 1
            except Exception as exc:  # noqa: BLE001 - 观察器不能中断采集
                print(f"[capture-error] {exc}")

        page.on("response", on_response)

        print(f"[probe] 已打开浏览器，请完成登录并浏览目标栏目（如「就业信息」）。")
        print(f"[probe] 窗口 {args.wait_minutes} 分钟，期间请点开若干篇文章列表和详情。")
        page.goto(args.portal_base_url, wait_until="domcontentloaded")
        try:
            page.wait_for_timeout(int(args.wait_minutes * 60 * 1000))
        except KeyboardInterrupt:
            print("[probe] 手动中断，收尾中...")

        browser.close()

    report = {
        "portal_base_url": args.portal_base_url,
        "captured_requests": captured,
        "candidate_column_ids": column_ids,
        "tips": "请人工核对 captured_requests，找出列表/详情接口的真实 URL 与参数，"
                "回填到 .env 的 PORTAL_BASE_URL / 端点与栏目配置。",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"[probe] 共捕获 {len(captured)} 个相关请求；结果已写入 {args.out}")
    print(f"[probe] 栏目 ID 候选: {json.dumps(column_ids, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
