import { useCallback, useContext } from "react";
import { UNSAFE_NavigationContext, useInRouterContext } from "react-router-dom";

/**
 * Router の中であれば `useNavigate`、外であれば URL 直書きへフォールバックするフック。
 *
 * Router 外で `useNavigate()` を呼ぶと「may be used only in the context of a <Router>」で
 * throw するため、`useInRouterContext()` を見てから **-router 内のときだけ** navigator を
 * 使う。Router 外でレンダリングされる既存テスト（`StudioWorkspace` の単体テスト等）が
 * 落ちないことを保証するのがこのフックの目的。
 *
 * `useNavigate()` を条件付きで呼ぶと「hook 呼び出し枠」は確保されず、
 * Router 内外でレンダリングが切り替わると React が
 * 「Rendered fewer hooks than expected」で落ちる。そのため `useNavigate` 自身が
 * 内部で読んでいる router コンテキストを直接読み、常に同じ個数の hook を呼ぶ。
 */
export function useOptionalNavigate(fallbackPath = "/"): (path: string) => void {
  const inRouter = useInRouterContext();
  // Router 外では null（型は非 null だが実行時は null になりうる）
  const navContext = useContext(UNSAFE_NavigationContext);
  const navigator = inRouter && navContext ? navContext.navigator : null;

  return useCallback(
    (path: string) => {
      const target = path || fallbackPath;

      if (navigator) {
        navigator.push(target);
        return;
      }

      // Router 外（テスト・プレビュー等）: ブラウザ API へフォールバック
      if (typeof window !== "undefined") {
        try {
          window.location.assign(target);
        } catch {
          // jsdom の "Not implemented: navigation" は想定内なので握りつぶす
        }
      }
    },
    [navigator, fallbackPath],
  );
}
