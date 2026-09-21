"""API 路由：五个第一周接口 + /healthz + 受环境变量保护的开发角色开关。

- 未知查询字段（GET 参数与 POST body）一律 400（接口字典第 6 节）。
- 权限在服务端 RolePolicy/Presenter 执行；前端只渲染 DTO。
- 开发角色开关只在 ENABLE_DEV_ROLE_SWITCH=true 时存在；生产访问返回 404。
"""

from __future__ import annotations

import io
import os

import json

from flask import Blueprint, jsonify, request, send_file, session

from ..domain.errors import ContractViolation
from ..domain.presenter import RecordPresenter, assert_no_restricted_fields, role_label
from ..domain.query_plan import MAX_PAGE_SIZE, QueryPlan
from ..domain.models import ProcessingEvent
from ..domain import role_policy
from ..repository.base import Repository
from ..search.answer_service import AnswerService
from ..search.query_parser import parse_query
from ..search.search_service import SearchService
from .exporter import filename, to_csv, to_xlsx

# GET /api/search 允许的查询参数（QueryPlan 白名单）
SEARCH_PARAMS = ("cohort", "education", "college", "major", "city",
                 "position_or_unit", "keywords", "page", "page_size")


def current_role() -> str:
    return role_policy.normalize_role(session.get("role"))


def current_user_id() -> str | None:
    """开发模式用显式用户标识模拟 CAS subject；生产不接受客户端伪造身份。"""
    role = current_role()
    if role == "guest":
        return None
    if role_policy.dev_role_switch_enabled():
        candidate = request.headers.get("X-Demo-User", "").strip()
        return candidate[:80] if candidate else f"demo-{role}"
    return session.get("user_id")


def _require_user(repo: Repository) -> str | None:
    role = current_role()
    user_id = current_user_id()
    if role == "guest" or not user_id:
        return None
    repo.ensure_user(user_id, role)  # type: ignore[attr-defined]
    return user_id


def build_api_blueprint(repo: Repository, search: SearchService,
                        answer: AnswerService) -> Blueprint:
    bp = Blueprint("api", __name__)
    presenter = RecordPresenter()
    sync_state = {"status": "not_configured", "task_id": None, "cursor": None, "success_count": 0, "failure_count": 0, "failure_reason": "SYNC_PROVIDER_NOT_CONFIGURED"}

    @bp.get("/api/search")
    def api_search():
        plan = _plan_from_args()
        role = current_role()
        outcome = search.search(plan, role)
        user_id = current_user_id()
        if user_id and not _incognito() and getattr(repo, "get_privacy", lambda _u: {"history_enabled": False})(user_id).get("history_enabled", False):
            repo.ensure_user(user_id, role)  # type: ignore[attr-defined]
            repo.add_search_history(user_id, json.dumps(plan.to_dict(), ensure_ascii=False, sort_keys=True))  # type: ignore[attr-defined]
        return jsonify({
            "query_plan": outcome.plan.to_dict(),
            "total": outcome.total,
            "page": outcome.page,
            "page_size": outcome.page_size,
            "results": outcome.items,
            "relaxations": outcome.relaxations,
            "empty_plan": outcome.empty_plan,
            "role": role,
        })

    @bp.get("/api/search/stats")
    def api_search_stats():
        """当前查询 + 当前角色可见记录的聚合统计（不泄露隐藏分组）。"""
        plan = _plan_from_args()
        return jsonify({
            "query_plan": plan.to_dict(),
            "role": current_role(),
            **search.stats(plan, current_role()),
        })

    @bp.post("/api/compare")
    def api_compare():
        """按 record_key 返回可并列比较的角色 DTO；最多 4 条，继续过 RolePolicy。"""
        body = _json_body(allowed_keys=("record_keys",))
        keys = body.get("record_keys")
        if not isinstance(keys, list) or not keys or len(keys) > 4:
            raise ContractViolation("body.record_keys: 必须是 1-4 个 record_key 的数组")
        role = current_role()
        records = []
        for key in keys:
            if not isinstance(key, str):
                raise ContractViolation("body.record_keys: 元素必须是字符串")
            record = repo.get_record(key)
            if record is None:
                return jsonify({"error": "not_found", "detail": f"记录不存在: {key}"}), 404
            if role_policy.published_only(role) and record.visibility != "published":
                return jsonify({"error": "not_found", "detail": f"记录不存在: {key}"}), 404
            article = repo.get_article(record.notice_id)
            evidence = repo.list_evidence_for_record(key)
            dto = presenter.present_full(record, article, evidence, role)
            assert_no_restricted_fields(dto, role)
            records.append(dto)
        return jsonify({"records": records, "role": role})

    @bp.get("/api/export")
    def api_export():
        """导出当前查询结果；CSV 扁平字段，XLSX 固定四个工作表。"""
        fmt = request.args.get("format", "csv").strip().lower()
        if fmt not in ("csv", "xlsx"):
            raise ContractViolation("format: 只允许 csv 或 xlsx")
        plan = _plan_from_args("format")
        role = current_role()
        # 导出全量当前匹配：逐页取完（page_size 上限沿用白名单约束）
        all_items: list[dict] = []
        page = 1
        while True:
            paged = QueryPlan.from_dict({**plan.to_dict(), "page": page,
                                         "page_size": MAX_PAGE_SIZE})
            outcome = search.search(paged, role)
            all_items.extend(outcome.items)
            if len(all_items) >= outcome.total or not outcome.items:
                break
            page += 1
        if fmt == "csv":
            data, mimetype = to_csv(all_items, role)
            download = filename("csv")
        else:
            evidence_map = {
                item["record_key"]: repo.list_evidence_for_record(item["record_key"])
                for item in all_items
            }
            data, mimetype = to_xlsx(all_items, evidence_map, role, plan.to_dict())
            download = filename("xlsx")
        return send_file(
            io.BytesIO(data),
            mimetype=mimetype,
            as_attachment=True,
            download_name=download,
        )

    @bp.post("/api/query/parse")
    def api_query_parse():
        body = _json_body(allowed_keys=("query", "mode"))
        text = body.get("query")
        if not isinstance(text, str) or len(text) > 200:
            raise ContractViolation("body.query: 必须是 1-200 字的字符串")
        plan, notes = parse_query(text)
        return jsonify({
            "query": text,
            "query_plan": plan.to_dict(),
            "source": "rule",
            "degraded": not answer.llm_configured(),
            "notes": notes,
            "role": current_role(),
        })

    @bp.post("/api/query/answer")
    def api_query_answer():
        body = _json_body(allowed_keys=("query", "mode"))
        text = body.get("query")
        if not isinstance(text, str) or not text.strip() or len(text) > 200:
            raise ContractViolation("body.query: 必须是 1-200 字的非空字符串")
        outcome = answer.answer(text, current_role())
        return jsonify({
            "answer": outcome.answer,
            "insufficient_evidence": outcome.insufficient_evidence,
            "degraded": outcome.degraded,
            "degraded_reason": outcome.degraded_reason,
            "citations": outcome.citations,
            "records": outcome.records,
            "query_plan": outcome.query_plan,
            "role": current_role(),
        })

    @bp.get("/api/records/<record_key>")
    def api_record_detail(record_key: str):
        role = current_role()
        record = repo.get_record(record_key)
        if record is None:
            return jsonify({"error": "not_found", "detail": "记录不存在"}), 404
        if role_policy.published_only(role) and record.visibility != "published":
            # 非管理员访问未发布记录：不暴露存在性，一律 404（越权即 4xx）
            return jsonify({"error": "not_found", "detail": "记录不存在"}), 404
        article = repo.get_article(record.notice_id)
        evidence = repo.list_evidence_for_record(record_key)
        dto = presenter.present_full(record, article, evidence, role)
        assert_no_restricted_fields(dto, role)
        return jsonify(dto)

    @bp.get("/api/auth/me")
    def api_auth_me():
        role = current_role()
        return jsonify({
            "role": role,
            "role_label": role_label(role),
            "capabilities": role_policy.role_capabilities(role),
            "authenticated": role != "guest",
            "dev_switch_enabled": role_policy.dev_role_switch_enabled(),
            "campus_original_asset_enabled": role_policy.campus_original_asset_enabled(),
        })

    # ---- 第二周：保存搜索、站内提醒、隐私与无痕 ----

    @bp.get("/api/saved-searches")
    def api_saved_searches_list():
        user_id = _require_user(repo)
        if not user_id:
            return jsonify({"error": "unauthorized", "detail": "需要校内登录"}), 401
        rows = repo.list_saved_searches(user_id)  # type: ignore[attr-defined]
        return jsonify({"items": [_saved_search_dto(row) for row in rows]})

    @bp.post("/api/saved-searches")
    def api_saved_searches_create():
        user_id = _require_user(repo)
        if not user_id:
            return jsonify({"error": "unauthorized", "detail": "需要校内登录"}), 401
        body = _json_body(("query_plan", "alert_frequency"))
        plan = QueryPlan.from_dict(body.get("query_plan"), allow_empty=False)
        frequency = body.get("alert_frequency", "weekly")
        if frequency not in ("off", "daily", "weekly"):
            raise ContractViolation("alert_frequency: 只允许 off、daily、weekly")
        row = repo.create_saved_search(user_id, json.dumps(plan.to_dict(), ensure_ascii=False, sort_keys=True), frequency)  # type: ignore[attr-defined]
        return jsonify(_saved_search_dto(row)), 201

    @bp.patch("/api/saved-searches/<int:saved_search_id>/alert")
    def api_saved_search_alert(saved_search_id: int):
        user_id = _require_user(repo)
        if not user_id:
            return jsonify({"error": "unauthorized", "detail": "需要校内登录"}), 401
        body = _json_body(("alert_frequency",))
        frequency = body.get("alert_frequency")
        if frequency not in ("off", "daily", "weekly"):
            raise ContractViolation("alert_frequency: 只允许 off、daily、weekly")
        row = repo.update_saved_alert(user_id, saved_search_id, frequency)  # type: ignore[attr-defined]
        if row is None:
            return jsonify({"error": "not_found"}), 404
        return jsonify(_saved_search_dto(row))

    @bp.delete("/api/saved-searches/<int:saved_search_id>")
    def api_saved_search_delete(saved_search_id: int):
        user_id = _require_user(repo)
        if not user_id:
            return jsonify({"error": "unauthorized", "detail": "需要校内登录"}), 401
        if not repo.delete_saved_search(user_id, saved_search_id):  # type: ignore[attr-defined]
            return jsonify({"error": "not_found"}), 404
        return jsonify({"deleted": True, "saved_search_id": saved_search_id})

    @bp.get("/api/me/privacy")
    def api_privacy_get():
        user_id = _require_user(repo)
        if not user_id:
            return jsonify({"error": "unauthorized", "detail": "需要校内登录"}), 401
        return jsonify(repo.get_privacy(user_id))  # type: ignore[attr-defined]

    @bp.patch("/api/me/privacy")
    def api_privacy_patch():
        user_id = _require_user(repo)
        if not user_id:
            return jsonify({"error": "unauthorized", "detail": "需要校内登录"}), 401
        body = _json_body(("history_enabled", "recommendation_enabled"))
        for key in body:
            if not isinstance(body[key], bool):
                raise ContractViolation(f"{key}: 必须是布尔值")
        return jsonify(repo.update_privacy(user_id, history_enabled=body.get("history_enabled"), recommendation_enabled=body.get("recommendation_enabled")))  # type: ignore[attr-defined]

    @bp.delete("/api/me/history")
    def api_history_delete():
        user_id = _require_user(repo)
        if not user_id:
            return jsonify({"error": "unauthorized", "detail": "需要校内登录"}), 401
        return jsonify({"deleted_count": repo.clear_search_history(user_id)})  # type: ignore[attr-defined]

    @bp.get("/api/me/insights")
    def api_insights():
        user_id = _require_user(repo)
        if not user_id:
            return jsonify({"error": "unauthorized", "detail": "需要校内登录"}), 401
        privacy = repo.get_privacy(user_id)  # type: ignore[attr-defined]
        if not privacy["recommendation_enabled"]:
            return jsonify({"enabled": False, "retention_days": 90, "insights": {}})
        return jsonify({"enabled": True, "retention_days": 90, "insights": repo.insight_summary(user_id)})  # type: ignore[attr-defined]

    @bp.get("/api/notifications")
    def api_notifications():
        user_id = _require_user(repo)
        if not user_id:
            return jsonify({"error": "unauthorized", "detail": "需要校内登录"}), 401
        return jsonify({"items": repo.list_notifications(user_id)})  # type: ignore[attr-defined]

    @bp.post("/api/admin/records/<record_key>/publish")
    def api_publish_record(record_key: str):
        if current_role() != "admin":
            return jsonify({"error": "forbidden"}), 403
        record = repo.get_record(record_key)
        if record is None:
            return jsonify({"error": "not_found"}), 404
        repo.set_visibility(record_key, "published")
        repo.record_event(ProcessingEvent(notice_id=record.notice_id, step="admin_publish", status="processed", occurred_at=_now_iso()))
        repo.emit_notifications_for_notice(record.notice_id, record.notice_id)  # type: ignore[attr-defined]
        return jsonify({"record_key": record_key, "visibility": "published"})

    @bp.post("/api/admin/records/<record_key>/withdraw")
    def api_withdraw_record(record_key: str):
        if current_role() != "admin":
            return jsonify({"error": "forbidden"}), 403
        record = repo.get_record(record_key)
        if record is None:
            return jsonify({"error": "not_found"}), 404
        repo.set_visibility(record_key, "withdrawn")
        repo.record_event(ProcessingEvent(notice_id=record.notice_id, step="admin_withdraw", status="processed", occurred_at=_now_iso()))
        return jsonify({"record_key": record_key, "visibility": "withdrawn"})

    @bp.post("/api/admin/sync")
    def api_admin_sync():
        """同步契约入口；未注入真实 CAS/Portal 时明确返回条件式阻塞。"""
        if current_role() != "admin":
            return jsonify({"error": "forbidden"}), 403
        if os.environ.get("SYNC_PROVIDER_CONFIGURED", "false").lower() != "true":
            return jsonify({"error": "sync_not_configured", "detail": "需要真实 Portal/CAS 配置，未伪造同步结果", "status": sync_state}), 503
        return jsonify({"error": "sync_runner_not_wired", "detail": "已配置资源但尚未绑定运行器", "status": sync_state}), 501

    @bp.get("/api/admin/sync/status")
    def api_admin_sync_status():
        if current_role() != "admin":
            return jsonify({"error": "forbidden"}), 403
        return jsonify(sync_state)

    # ---- 开发角色开关：生产环境 404（附录 G G5） ----

    @bp.post("/api/dev/role")
    def api_dev_role_set():
        if not role_policy.dev_role_switch_enabled():
            return jsonify({"error": "not_found"}), 404
        body = _json_body(allowed_keys=("role",))
        role = body.get("role")
        if role not in role_policy.ROLES:
            raise ContractViolation(
                f"body.role: 只允许 {list(role_policy.ROLES)}"
            )
        session["role"] = role
        return jsonify({"role": role, "role_label": role_label(role)})

    @bp.delete("/api/dev/role")
    def api_dev_role_reset():
        if not role_policy.dev_role_switch_enabled():
            return jsonify({"error": "not_found"}), 404
        session.pop("role", None)
        return jsonify({"role": "guest"})

    # ---- 健康检查 ----

    @bp.get("/healthz")
    def healthz():
        db_ok = repo.database_ok()
        components = {
            "database": "ok" if db_ok else "error",
            "search": "ok",
            "llm": "configured" if answer.llm_configured() else "not_configured",
            "embedding": "disabled_by_decision",
        }
        status = 200 if db_ok else 503
        return jsonify({
            "status": "ok" if db_ok else "degraded",
            "components": components,
        }), status

    return bp


# ---- 请求处理辅助 ----


def _plan_from_args(*extra_allowed: str) -> QueryPlan:
    """从 GET 查询参数构造 QueryPlan；未知参数与非法值一律 400。

    extra_allowed 是个别接口自身的控制参数（如 export 的 format）。
    """
    _reject_unknown_params(*extra_allowed)
    raw = {name: request.args.get(name) for name in SEARCH_PARAMS
           if request.args.get(name) not in (None, "")}
    if "page" in raw:
        raw["page"] = _to_int(raw["page"], "page")
    if "page_size" in raw:
        raw["page_size"] = _to_int(raw["page_size"], "page_size")
    if "keywords" in raw:
        raw["keywords"] = [
            token for token in raw["keywords"].replace("，", " ").replace(",", " ").split()
        ]
    return QueryPlan.from_dict(raw)


def _reject_unknown_params(*extra_allowed: str) -> None:
    unknown = sorted(set(request.args) - set(SEARCH_PARAMS) - set(extra_allowed))
    if unknown:
        raise ContractViolation(f"存在不允许的查询参数 {unknown}")


def _json_body(allowed_keys: tuple[str, ...]) -> dict:
    body = request.get_json(silent=True)
    if body is None:
        raise ContractViolation("请求体必须是 JSON 对象")
    if not isinstance(body, dict):
        raise ContractViolation("请求体必须是 JSON 对象")
    unknown = sorted(set(body) - set(allowed_keys))
    if unknown:
        raise ContractViolation(f"请求体存在不允许的字段 {unknown}")
    return body


def _to_int(value: str, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ContractViolation(f"{name}: 必须是整数") from exc


def _incognito() -> bool:
    return request.headers.get("X-Incognito-Mode", "0") == "1"


def _saved_search_dto(row: dict) -> dict:
    return {
        "saved_search_id": row["saved_search_id"],
        "query_plan": json.loads(row["query_plan_json"]),
        "alert_frequency": row["alert_frequency"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().astimezone().isoformat(timespec="seconds")
