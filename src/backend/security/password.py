import logging

import bcrypt

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """平文パスワードとハッシュを照合する。

    bcrypt.checkpw は、hashed_password が不正な bcrypt 形式でない場合などに
    ValueError を発生させる。想定外の例外はログに出力しつつ False を返す。
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError) as exc:
        # ハッシュ形式が不正など、入力データの問題
        logger.debug("Password verification input error: %s", exc)
        return False
    except Exception as exc:  # 想定外の bcrypt 内部エラー等
        logger.exception("Password verification raised unexpected %s", type(exc).__name__)
        return False
