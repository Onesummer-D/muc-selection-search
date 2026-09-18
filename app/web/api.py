"""API 路由：五个第一周接口 + /healthz + 受环境变量保护的开发角色开关。

- 未知查询字段（GET 参数与 POST body）一律 400（接口字典第 6 节）。
- 权限在服务端 RolePolicy/Presenter 执行；前端只渲染 DTO。
- 开发角色开关只在 ENABLE_DEV_ROLE_SWITCH=true 时存在；生产访问返回 404。
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from ..domain.errors import ContractViolation
from ..domain.presenter import RecordPresenter, assert_no_restricted_fields, role_label
from ..domain.query_plan import QueryPlan
from ..domain import role_policy
from ..repository.base import Repository
from ..search.answer_service import AnswerService
from ..search.query_parser import parse_query
from ..search.search_service import SearchService

# GET /api/search 允许的查询参数（QueryPlan 白名单）
SEARCH_PARAMS = ("cohort", "education", "college", "major", "city",
                 "position_or_unit", "keywords", "page", "page_size")


def current_role() -> str:
    return role_policy.normalize_role(session.get("role"))


def build_api_blueprint(repo: Repository, search: SearchService,
                        answer: AnswerService) -> Blueprint:
    bp = Blueprint("api", __name__)
    presenter = RecordPresenter()

    @bp.get("/api/search")
    def api_search():
        _reject_unknown_params()
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
        plan = QueryPlan.from_dict(raw)
        outcome = search.search(plan, current_role())
        return jsonify({
            "query_plan": outcome.plan.to_dict(),
            "total": outcome.total,
            "page": outcome.page,
            "page_size": outcome.page_size,
            "results": outcome.items,
            "relaxations": outcome.relaxations,
            "empty_plan": outcome.empty_plan,
            "role": current_role(),
        })

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


def _reject_unknown_params() -> None:
    unknown = sorted(set(request.args) - set(SEARCH_PARAMS))
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
