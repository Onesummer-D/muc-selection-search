"""应用工厂：装配 Repository / SearchService / AnswerService 与错误映射。

生产模式把 Vite 构建产物（frontend/dist）与 Flask 同源部署；
开发模式由 Vite 代理 /api 到本服务（附录 G G1）。
"""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from werkzeug.exceptions import NotFound

from ..domain.errors import ContractViolation, MissingArticleError, StorageIntegrityError
from ..repository.sqlite_repository import SQLiteRepository
from ..search.answer_service import AnswerService
from ..search.llm_provider import LLMProvider
from ..search.search_service import SearchService
from .api import build_api_blueprint

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_env_file(path: Path) -> None:
    """极简 .env 加载：KEY=VALUE，# 注释；已存在的环境变量优先，不覆盖。

    .env 只存放本机密钥与配置，已在 .gitignore 中，永不进入仓库。
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def create_app(
    repository: SQLiteRepository | None = None,
    llm_provider: "LLMProvider | None" = None,
) -> Flask:
    load_env_file(PROJECT_ROOT / ".env")
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    app.config["APP_ENV"] = os.environ.get("APP_ENV", "development")
    app.config["JSON_AS"] = "utf-8"
    app.json.ensure_ascii = False

    repo = repository or SQLiteRepository(
        os.environ.get("DATABASE_URL", "data/app.db")
    )
    search = SearchService(repo)
    answer = AnswerService(repo, search, llm_provider=llm_provider)
    app.extensions["repository"] = repo
    app.extensions["search"] = search
    app.extensions["answer"] = answer

    app.register_blueprint(build_api_blueprint(repo, search, answer))

    @app.errorhandler(ContractViolation)
    def on_contract_violation(exc: ContractViolation):
        return jsonify({"error": "invalid_request", "detail": str(exc)}), 400

    @app.errorhandler(MissingArticleError)
    def on_missing_article(exc: MissingArticleError):
        return jsonify({"error": "missing_article", "detail": str(exc)}), 409

    @app.errorhandler(StorageIntegrityError)
    def on_storage_error(exc: StorageIntegrityError):
        # 不向客户端返回内部堆栈
        return jsonify({"error": "storage_error", "detail": "存储完整性错误，请联系管理员"}), 500

    @app.errorhandler(404)
    def on_not_found(_exc):
        return jsonify({"error": "not_found"}), 404

    @app.errorhandler(405)
    def on_method_not_allowed(_exc):
        return jsonify({"error": "method_not_allowed"}), 405

    _register_frontend(app)
    return app


def _register_frontend(app: Flask) -> None:
    """生产模式：同源托管 frontend/dist；目录不存在时跳过（开发由 Vite 提供页面）。"""
    dist = PROJECT_ROOT / "frontend" / "dist"
    index_file = dist / "index.html"
    if not index_file.exists():
        return

    @app.route("/", defaults={"asset_path": ""})
    @app.route("/<path:asset_path>")
    def frontend(asset_path: str):
        if asset_path:
            # send_from_directory 同时防御路径穿越；不存在的路径回落到 SPA 入口
            try:
                return send_from_directory(dist, asset_path)
            except NotFound:
                pass
        return index_file.read_text(encoding="utf-8"), 200, {
            "Content-Type": "text/html; charset=utf-8"
        }
