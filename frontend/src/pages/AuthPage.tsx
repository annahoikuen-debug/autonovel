import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

type AuthMode = "login" | "register";

interface AuthPageProps {
    mode: AuthMode;
}

/** ログイン／新規登録の共通フォーム。 */
export function AuthPage({ mode }: AuthPageProps) {
    const { token, login, register } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();

    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [displayName, setDisplayName] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);

    // `?next=/studio` があればログイン後にそこへ戻す。
    const nextPath = new URLSearchParams(location.search).get("next");
    const redirectTo = nextPath && nextPath.startsWith("/") ? nextPath : "/";

    // すでにログイン済みならフォームを見せない。
    useEffect(() => {
        if (token) {
            navigate(redirectTo, { replace: true });
        }
    }, [token, navigate, redirectTo]);

    const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setError(null);
        setSubmitting(true);
        try {
            if (mode === "register") {
                await register(email, password, displayName);
            } else {
                await login(email, password);
            }
            navigate(redirectTo, { replace: true });
        } catch (err) {
            setError(err instanceof Error ? err.message : "認証に失敗しました");
        } finally {
            setSubmitting(false);
        }
    };

    const isRegister = mode === "register";

    return (
        <div
            className="card"
            data-testid={isRegister ? "register-page" : "login-page"}
            style={{ maxWidth: "420px", margin: "48px auto" }}
        >
            <h2 style={{ marginTop: 0 }}>{isRegister ? "新規登録" : "ログイン"}</h2>
            <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>
                {isRegister
                    ? "メールアドレスとパスワードを登録すると、すぐに執筆を始められます。"
                    : "登録済みのメールアドレスとパスワードを入力してください。"}
            </p>

            <form onSubmit={handleSubmit}>
                {isRegister && (
                    <div className="form-group">
                        <label className="label" htmlFor="display-name">
                            表示名
                        </label>
                        <input
                            id="display-name"
                            className="input"
                            type="text"
                            autoComplete="nickname"
                            value={displayName}
                            onChange={(e) => setDisplayName(e.target.value)}
                            required
                        />
                    </div>
                )}

                <div className="form-group">
                    <label className="label" htmlFor="email">
                        メールアドレス
                    </label>
                    <input
                        id="email"
                        className="input"
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                    />
                </div>

                <div className="form-group">
                    <label className="label" htmlFor="password">
                        パスワード
                    </label>
                    <input
                        id="password"
                        className="input"
                        type="password"
                        autoComplete={isRegister ? "new-password" : "current-password"}
                        minLength={isRegister ? 8 : undefined}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                    />
                    {isRegister && (
                        <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginTop: "6px" }}>
                            8 文字以上で設定してください。
                        </p>
                    )}
                </div>

                {error && (
                    <p role="alert" className="toast toast--error" style={{ marginBottom: "16px" }}>
                        {error}
                    </p>
                )}

                <button className="btn btn-primary" type="submit" disabled={submitting} style={{ width: "100%" }}>
                    {submitting ? "処理中..." : isRegister ? "登録して始める" : "ログイン"}
                </button>
            </form>

            <p style={{ marginTop: "20px", fontSize: "0.9rem", color: "var(--text-muted)" }}>
                {isRegister ? (
                    <>
                        すでにアカウントをお持ちですか？ <Link to="/login">ログイン</Link>
                    </>
                ) : (
                    <>
                        アカウントをお持ちでないですか？ <Link to="/register">新規登録</Link>
                    </>
                )}
            </p>
        </div>
    );
}

export function LoginPage() {
    return <AuthPage mode="login" />;
}

export function RegisterPage() {
    return <AuthPage mode="register" />;
}
