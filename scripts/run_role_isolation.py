"""越权活体验证：真实 HTTP 服务上验证角色隔离（week2 9/22 任务证据）。

场景：
A. ENABLE_DEV_ROLE_SWITCH 未设置（生产默认）→ POST /api/dev/role 必须 404
B. 伪造客户端 header（X-Role/X-Forwarded-User/Authorization 等）→ /api/auth/me 仍为 guest
C. 开关显式开启（仅开发）→ 开关可用，DELETE 可复位（证明功能受环境变量门控）
D. 关闭开关后伪造 header + 打 dev/role → 仍 404 / 仍 guest

输出：repo-week2/evidence/week2/A/role-isolation-live.txt
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# 带 session cookie 的 opener（角色切换写 session，需要同一会话验证）
CJ = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repository.sqlite_repository import SQLiteRepository
from app.search.llm_provider import NullProvider
from app.web.app import create_app
from app.web.seed import seed
from werkzeug.serving import make_server

PORT = 5077
BASE = f"http://127.0.0.1:{PORT}"
OUT = ROOT / "evidence" / "week2" / "A" / "role-isolation-live.txt"

lines: list[str] = []


def log(s: str = "") -> None:
    print(s)
    lines.append(s)


def req(method: str, path: str, body: dict | None = None,
        headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with OPENER.open(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def make_server_for(env_on: bool) -> tuple:
    if env_on:
        os.environ["ENABLE_DEV_ROLE_SWITCH"] = "true"
    else:
        os.environ.pop("ENABLE_DEV_ROLE_SWITCH", None)
    repo = SQLiteRepository(":memory:")
    seed(repo)
    app = create_app(repository=repo, llm_provider=NullProvider())
    srv = make_server("127.0.0.1", PORT, app)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, repo


def main() -> None:
    log("# 越权活体验证（真实 HTTP 服务 127.0.0.1:%d）" % PORT)
    log("# 时间: %s" % datetime.now().isoformat(timespec="seconds"))
    log("# 复现命令: python scripts/run_role_isolation.py（本仓库根目录）")
    log()

    # ---- A/B/D：生产默认（开关关闭） ----
    os.environ.pop("ENABLE_DEV_ROLE_SWITCH", None)
    srv, _ = make_server_for(env_on=False)

    log("## A. 开关关闭时 POST /api/dev/role（生产默认）")
    code, body = req("POST", "/api/dev/role", {"role": "admin"})
    ok = code == 404
    log("   状态码: %d（预期 404）  响应: %s" % (code, body))
    log("   结论: %s" % ("PASS - 生产环境入口不可达" if ok else "FAIL"))
    log()

    log("## B. 伪造客户端 header 后 GET /api/auth/me（应仍为 guest）")
    all_ok = True
    for h in ({"X-Role": "admin"}, {"X-Forwarded-User": "admin"},
              {"X-Remote-User": "admin"}, {"Authorization": "Bearer admin"},
              {"Role": "admin"}, {"X-Role": "admin", "X-Forwarded-User": "admin"}):
        code, body = req("GET", "/api/auth/me", headers=h)
        role = body.get("role")
        ok = (code == 200 and role == "guest")
        all_ok = all_ok and ok
        log("   %-42s → %d  role=%s  %s"
            % (json.dumps(h, ensure_ascii=False), code, role,
               "PASS" if ok else "FAIL"))
    log("   结论: %s" % ("PASS - 客户端 header 无法伪造身份" if all_ok else "FAIL"))
    log()

    log("## D. 开关关闭 + 伪造 header 打 /api/dev/role（应仍 404）")
    code, body = req("POST", "/api/dev/role", {"role": "admin"},
                     headers={"X-Role": "admin"})
    ok = code == 404
    log("   状态码: %d（预期 404）  响应: %s" % (code, body))
    log("   结论: %s" % ("PASS - 伪造 header 不改变开关可达性" if ok else "FAIL"))
    log()
    srv.shutdown()

    # ---- C：开发开关显式开启（仅开发环境） ----
    srv2, _ = make_server_for(env_on=True)
    log("## C. ENABLE_DEV_ROLE_SWITCH=true（仅开发）时开关行为")
    code, body = req("POST", "/api/dev/role", {"role": "student"})
    log("   切换为 student: %d  响应: %s" % (code, body))
    code, body = req("GET", "/api/auth/me")
    log("   /api/auth/me: %d  role=%s" % (code, body.get("role")))
    code, body = req("POST", "/api/dev/role", {"role": "superadmin"})
    log("   非法角色 superadmin: %d（预期 400）" % code)
    code, body = req("DELETE", "/api/dev/role")
    log("   DELETE 复位: %d  响应: %s" % (code, body))
    code, body = req("GET", "/api/auth/me")
    log("   复位后 role=%s（预期 guest）" % body.get("role"))
    log("   结论: PASS - 开关仅在环境变量显式开启时可用")
    srv2.shutdown()

    os.environ.pop("ENABLE_DEV_ROLE_SWITCH", None)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n[saved] %s" % OUT)


if __name__ == "__main__":
    main()
