"""领域异常。

ContractViolation：bundle 内容违反 v1 契约，发生在任何写入之前。
StorageIntegrityError / MissingArticleError：数据库完整性约束失败，
由仓储层把 sqlite3.IntegrityError 翻译成领域错误，上层不依赖 sqlite3。
"""


class ContractViolation(ValueError):
    """bundle 内容违反 article_bundle.v1 / extraction_bundle.v1 契约。"""


class StorageIntegrityError(RuntimeError):
    """数据库完整性约束失败（CHECK、唯一键等）。"""


class MissingArticleError(StorageIntegrityError):
    """extraction bundle 引用的 notice_id 尚未导入对应 article bundle。"""
