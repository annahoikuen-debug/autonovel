import React from "react";

/**
 * 予期しないレンダリングエラー用のエラーバウンダリ。
 *
 * 認証トークンは localStorage に載っており、スタックトレースや
 * localStorage をそのまま含む例外文字列を画面に投げると情報漏えいに繋がる。
 * そのため **スタックトレースは一切出さず**、例外メッセージは
 * HTML 記号を含まない・長さ 200 文字以内のみ表示し、それ以外は既定文言に換える。
 */

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/** 表示用の安全なメッセージ（生の例外文字列をそのまま載せない） */
function safeMessage(error: Error): string {
  const message = (error.message || "").trim();
  // 長すぎる / HTML らしき文字列は、そのまま innerHTML に入れない
  if (!message || message.length > 200 || /[<>]/.test(message)) {
    return "予期しないエラーが発生しました。";
  }
  return message;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // 監視に回せるようログには残す（画面には出さない）
    console.error("Unhandled UI error:", error, errorInfo.componentStack);
  }

  private handleRetry = () => {
    this.setState({ error: null });
  };

  private handleReload = () => {
    window.location.reload();
  };

  render() {
    const { error } = this.state;
    if (!error) return <>{this.props.children}</>;

    return (
      <div
        role="alert"
        data-testid="error-boundary"
        style={{
          minHeight: "60vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "12px",
          padding: "32px",
          color: "var(--text-primary, #1a1a1a)",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "1.25rem" }}>画面を表示できませんでした</h2>
        <p style={{ margin: 0, opacity: 0.8 }}>{safeMessage(error)}</p>
        <div style={{ display: "flex", gap: "8px" }}>
          <button type="button" onClick={this.handleRetry} data-testid="error-boundary-retry">
            もう一度描画する
          </button>
          <button type="button" onClick={this.handleReload} data-testid="error-boundary-reload">
            ページを再読み込み
          </button>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;