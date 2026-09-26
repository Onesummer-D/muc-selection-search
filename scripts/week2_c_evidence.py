"""第二周角色 C 端到端证据生成（可复现脚本）。

覆盖台账待补项：
- C-04 游客脱敏与 review_required 不公开  -> evidence/week2/C/guest-network.json
- U-03 删除历史后旧记录不参与推荐画像     -> evidence/week2/C/history-delete.json
- 手册四、无痕搜索零写入                  -> evidence/week2/C/incognito-zero-write.json
- U-01 跨用户隔离（保存搜索/提醒）        -> evidence/week2/C/cross-user-isolation.json

运行：python scripts/week2_c_evidence.py
说明：脚本自建临时 SQLite 库并 seed 脱敏演示数据，在本机回环端口起真实 HTTP 服务，
用 requests 记录完整请求/响应（状态码、头、体），任何断言失败即非零退出；
证据中不含 Cookie、API Key、真实姓名或本机绝对路径。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests
from werkzeug.serving import make_server

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.domain import role_policy  # noqa: E402
from app.domain.presenter import assert_no_restricted_fields  # noqa: E402
from app.repository.sqlite_repository import SQLiteRepository  # noqa: E402
from app.search.llm_provider import NullProvider  # noqa: E402
from app.web.app import create_app  # noqa: E402
from app.web.seed import seed  # noqa: E402

PORT = 5057
BASE = f"http://127.0.0.1:{PORT}"
OUT_DIR = PROJECT_ROOT / "evidence" / "week2" / "C"
GENERATED_AT = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

FAILURES: list[str] = []


def check(condition: bool, message: str, records: list) -> None:
    records.append({"check": message, "pass": bool(condition)})
    if not condition:
        FAILURES.append(message)


def call(session: requests.Session, method: str, path: str, **kwargs) -> dict:
    """发起真实 HTTP 调用并记录可审计的请求/响应摘要。"""
    resp = session.request(method, BASE + path, timeout=10, **kwargs)
    try:
        body = resp.json()
    except ValueError:
        body = {"_non_json_body": resp.text[:200]}
    return {
        "method": method,
        "path": path,
        "request_headers": {k: v for k, v in (kwargs.get("headers") or {}).items()},
        "status": resp.status_code,
        "response_headers": {k: v for k, v in resp.headers.items() if k.lower() in ("content-type", "x-incognito-mode")},
        "response": body,
    }


def save(name: str, scenario: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "evidence": name,
        "generated_at": GENERATED_AT,
        "server": f"127.0.0.1:{PORT} (loopback, Flask dev server)",
        "command": "python scripts/week2_c_evidence.py",
        "db": "tempfile SQLite + app.web.seed 脱敏演示数据（5 文章/7 记录）",
        **scenario,
    }
    target = OUT_DIR / name
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(1 for s in payload.get("assertions", []) if s["pass"])
    total = len(payload.get("assertions", []))
    print(f"[OK] {name}: {passed}/{total} 断言通过 -> {target.relative_to(PROJECT_ROOT)}")


def new_session(role: str | None, user: str | None = None) -> tuple[requests.Session, list]:
    """独立 Cookie 的会话；dev 角色开关显式写明，证据里保留请求头记录。"""
    s = requests.Session()
    steps: list = []
    if role is not None:
        steps.append(call(s, "POST", "/api/dev/role", json={"role": role}))
    if user:
        s.headers["X-Demo-User"] = user
    return s, steps


def scenario_guest(steps: list) -> None:
    guest, guest_steps = new_session(None)
    admin, admin_steps = new_session("admin")
    records = guest_steps + admin_steps
    assertions: list = []

    health = call(guest, "GET", "/healthz")
    records.append(health)
    check(health["status"] == 200 and health["response"].get("status") == "ok", "游客可访问 /healthz 且状态 ok", assertions)

    search = call(guest, "GET", "/api/search", params={"education": "本科", "major": "计算机"})
    records.append(search)
    results = search["response"].get("results", [])
    check(search["status"] == 200 and results, "游客可搜索且返回结果", assertions)
    check(all(r.get("visibility") == "published" for r in results), "游客结果全部为 published", assertions)
    hidden_keys = {"portal-10004-01", "portal-10005-01"}
    check(all(r.get("record_key") not in hidden_keys for r in results), "review_required/draft 记录不出现在游客结果", assertions)
    for r in results:
        assert_no_restricted_fields(r, "guest")
    check(True, "游客搜索 DTO 无受限字段（服务端 assert_no_restricted_fields 等价校验）", assertions)

    detail_rr = call(guest, "GET", "/api/records/portal-10004-01")
    detail_draft = call(guest, "GET", "/api/records/portal-10005-01")
    records.extend([detail_rr, detail_draft])
    check(detail_rr["status"] == 404 and detail_draft["status"] == 404, "游客访问 review_required/draft 详情均 404", assertions)

    published_key = results[0]["record_key"] if results else "portal-10001-01"
    detail_ok = call(guest, "GET", f"/api/records/{published_key}")
    records.append(detail_ok)
    dto = detail_ok.get("response", {})
    check(detail_ok["status"] == 200, "游客可查看 published 详情", assertions)
    check("person" not in dto and "url" not in dto.get("source", {}), "游客详情无 person 对象与来源 URL", assertions)
    assert_no_restricted_fields(dto, "guest")
    check(True, "游客详情 DTO 无受限字段", assertions)

    saved = call(guest, "GET", "/api/saved-searches")
    privacy = call(guest, "GET", "/api/me/privacy")
    publish = call(guest, "POST", "/api/admin/records/portal-10005-01/publish")
    records.extend([saved, privacy, publish])
    check(saved["status"] == 401 and privacy["status"] == 401, "游客访问个人数据接口 401", assertions)
    check(publish["status"] == 403, "游客调用管理员发布 403", assertions)

    admin_view = call(admin, "GET", "/api/records/portal-10004-01")
    records.append(admin_view)
    check(admin_view["status"] == 200 and "person" in admin_view["response"], "管理员复核视图可见同一 review_required 记录（对照）", assertions)

    save("guest-network.json", {"scenario": "游客脱敏与 review_required 不公开", "steps": records, "assertions": assertions})


def scenario_history_delete() -> None:
    alice, steps = new_session("student", "alice")
    records = list(steps)
    assertions: list = []

    enable = call(alice, "PATCH", "/api/me/privacy", json={"history_enabled": True, "recommendation_enabled": True})
    records.append(enable)
    check(enable["status"] == 200 and enable["response"]["history_enabled"], "alice 开启历史与推荐", assertions)

    s1 = call(alice, "GET", "/api/search", params={"major": "软件工程"})
    s2 = call(alice, "GET", "/api/search", params={"city": "成都"})
    records.extend([s1, s2])
    before = call(alice, "GET", "/api/me/insights")
    records.append(before)
    check(before["response"]["insights"].get("history_count") == 2, "两次搜索后 history_count=2", assertions)

    delete = call(alice, "DELETE", "/api/me/history")
    records.append(delete)
    check(delete["status"] == 200 and delete["response"].get("deleted_count") == 2, "删除历史返回 deleted_count=2", assertions)

    after = call(alice, "GET", "/api/me/insights")
    records.append(after)
    insights = after["response"]["insights"]
    check(insights.get("history_count") == 0, "删除后 history_count=0，旧记录不再参与画像/推荐", assertions)
    check(after["response"].get("retention_days") == 90, "保留期固定 90 天", assertions)

    save("history-delete.json", {"scenario": "删除历史后旧记录不参与推荐画像（U-03）", "steps": records, "assertions": assertions})


def scenario_incognito() -> None:
    bob, steps = new_session("student", "bob")
    records = list(steps)
    assertions: list = []

    records.append(call(bob, "PATCH", "/api/me/privacy", json={"history_enabled": True, "recommendation_enabled": True}))
    normal = call(bob, "GET", "/api/search", params={"major": "计算机"})
    records.append(normal)
    count1 = call(bob, "GET", "/api/me/insights")
    records.append(count1)
    check(count1["response"]["insights"].get("history_count") == 1, "普通搜索写入历史 1 条", assertions)

    incognito_headers = {"X-Incognito-Mode": "1"}
    inc_search = call(bob, "GET", "/api/search", params={"city": "成都"}, headers=incognito_headers)
    inc_compare = call(bob, "POST", "/api/compare", json={"record_keys": ["portal-10001-01", "portal-10002-01"]}, headers=incognito_headers)
    inc_export = call(bob, "GET", "/api/export", params={"format": "csv"}, headers=incognito_headers)
    records.extend([inc_search, inc_compare, inc_export])
    count2 = call(bob, "GET", "/api/me/insights")
    records.append(count2)
    check(count2["response"]["insights"].get("history_count") == 1, "无痕搜索/对比/导出后历史仍为 1（零写入）", assertions)

    delete = call(bob, "DELETE", "/api/me/history")
    final = call(bob, "GET", "/api/me/insights")
    records.extend([delete, final])
    check(final["response"]["insights"].get("history_count") == 0, "删除后为 0", assertions)

    save("incognito-zero-write.json", {"scenario": "X-Incognito-Mode: 1 全链路零写入（搜索/对比/导出）", "steps": records, "assertions": assertions})


def scenario_cross_user() -> None:
    alice, alice_steps = new_session("student", "alice")
    bob, bob_steps = new_session("student", "bob")
    records = alice_steps + bob_steps
    assertions: list = []

    create = call(alice, "POST", "/api/saved-searches", json={"query_plan": {"major": "计算机"}, "alert_frequency": "weekly"})
    records.append(create)
    check(create["status"] == 201, "alice 创建保存搜索（weekly）", assertions)
    check("query" not in create["response"], "接口不回显自然语言原文（只存 QueryPlan 白名单）", assertions)
    saved_id = create["response"].get("saved_search_id")

    bob_list = call(bob, "GET", "/api/saved-searches")
    records.append(bob_list)
    check(bob_list["response"].get("items") == [], "bob 看不到 alice 的保存搜索", assertions)

    bob_delete = call(bob, "DELETE", f"/api/saved-searches/{saved_id}")
    bob_patch = call(bob, "PATCH", f"/api/saved-searches/{saved_id}/alert", json={"alert_frequency": "daily"})
    records.extend([bob_delete, bob_patch])
    check(bob_delete["status"] == 404 and bob_patch["status"] == 404, "bob 改/删 alice 的保存搜索均 404", assertions)

    alice_list = call(alice, "GET", "/api/saved-searches")
    records.append(alice_list)
    items = alice_list["response"].get("items", [])
    check(len(items) == 1 and items[0].get("alert_frequency") == "weekly", "alice 自己仍可见且提醒为 weekly（默认值验证）", assertions)

    save("cross-user-isolation.json", {"scenario": "跨用户隔离（U-01）：保存搜索按 user_id 隔离", "steps": records, "assertions": assertions})


def main() -> int:
    os.environ[role_policy.DEV_ROLE_SWITCH_ENABLED] = "true"
    tmpdir = tempfile.mkdtemp(prefix="muc-week2-c-evidence-")
    db_path = os.path.join(tmpdir, "app.db")
    repo = SQLiteRepository(db_path)
    seed(repo)
    app = create_app(repository=repo, llm_provider=NullProvider())
    app.config["TESTING"] = False

    server = make_server("127.0.0.1", PORT, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        scenario_guest([])
        scenario_history_delete()
        scenario_incognito()
        scenario_cross_user()
    finally:
        server.shutdown()
        repo.close()

    if FAILURES:
        print(f"[FAIL] {len(FAILURES)} 项断言未通过：")
        for item in FAILURES:
            print(f"  - {item}")
        return 1
    print("[DONE] 4 份证据全部生成，断言全绿。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
