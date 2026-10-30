from __future__ import annotations

"""パッチレビュー ステータス 列挙互換クラス。"""


class PatchReviewStatus(str):
    GENERATED = "generated"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"
    EXPIRED = "expired"
