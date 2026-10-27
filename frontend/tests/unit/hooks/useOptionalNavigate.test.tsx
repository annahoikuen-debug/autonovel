/**
 * 回帰テスト: useOptionalNavigate は hook を条件付きで呼ばない（D9）。
 *
 * 以前は `inRouter ? useNavigate() : null` という「hook 呼び出し枠を確保しない」実装で、
 * eslint-disable と「枠は確保されている」というコメントで誤魔化していた。
 * 同じコンポーネントが Router 外で描画されたあとに Router 内で再レンダリングされると、
 * hook の数が変わり React が「Rendered fewer/more hooks than expected」で落ちる。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React, { useContext } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import {
  MemoryRouter,
  Route,
  Routes,
  UNSAFE_LocationContext,
  UNSAFE_NavigationContext,
  useLocation,
} from "react-router-dom";
import { useOptionalNavigate } from "../../../src/hooks/useOptionalNavigate";

/** react-router が内部で navigator を取り出すために読む context 実体 */
interface NavContextLike {
  navigator: { push: (to: unknown) => void };
}
interface LocationContextLike {
  location: unknown;
  navigationType: unknown;
}

let pushed: string[] = [];
let navContext: NavContextLike | null = null;
let locationContext: LocationContextLike | null = null;

/**
 * 実際の MemoryRouter から context を採取する（push 呼び出しは記録する）。
 * `useInRouterContext()` は LocationContext を見るため、両方採取する。
 */
function captureRouterContexts() {
  function Capture() {
    navContext = useContext(UNSAFE_NavigationContext) as unknown as NavContextLike | null;
    locationContext = useContext(UNSAFE_LocationContext) as unknown as LocationContextLike | null;
    return null;
  }
  render(
    <MemoryRouter>
      <Capture />
    </MemoryRouter>,
  );
  cleanup();

  if (!navContext) throw new Error("navigation context を採取できなかった");
  const real = navContext;
  navContext = {
    ...real,
    navigator: {
      ...real.navigator,
      push: (to: unknown) => {
        pushed.push(String(to));
      },
    },
  };
}

function Probe() {
  const navigate = useOptionalNavigate("/fallback");
  return (
    <button type="button" data-testid="go" onClick={() => navigate("/next")}>
      遷移
    </button>
  );
}

/**
 * Router の有無だけを差し替える。Provider の要素型を固定しているので Probe の
 * インスタンスは保たれる（＝hook 数だけが変化する本来の状況を再現できる）。
 */
function Host({ withRouter }: { withRouter: boolean }) {
  return (
    <UNSAFE_LocationContext.Provider value={withRouter ? locationContext : null}>
      <UNSAFE_NavigationContext.Provider value={withRouter ? navContext : null}>
        <Probe />
      </UNSAFE_NavigationContext.Provider>
    </UNSAFE_LocationContext.Provider>
  );
}

let assignSpy: ReturnType<typeof vi.fn>;
let originalLocation: Location;

beforeEach(() => {
  pushed = [];
  navContext = null;
  locationContext = null;
  assignSpy = vi.fn();
  originalLocation = window.location;
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...originalLocation, assign: assignSpy },
  });
});

afterEach(() => {
  Object.defineProperty(window, "location", {
    configurable: true,
    value: originalLocation,
  });
  cleanup();
});

function click() {
  act(() => {
    screen.getByTestId("go").click();
  });
}

describe("useOptionalNavigate", () => {
  it("Router 外でも描画でき、URL 直書きへフォールバックする", () => {
    render(<Host withRouter={false} />);
    expect(screen.getByTestId("go")).toBeInTheDocument();

    click();

    expect(assignSpy).toHaveBeenCalledWith("/next");
    expect(pushed).toEqual([]);
  });

  it("Router 外 → 内 → 外 と切り替えてもクラッシュせず hook 数が変わらない", () => {
    captureRouterContexts();

    const { rerender } = render(<Host withRouter={false} />);
    click();
    expect(assignSpy).toHaveBeenCalledTimes(1);

    // Router 外 → Router 内（同じ Probe インスタンスのまま再レンダリング）
    expect(() => rerender(<Host withRouter />)).not.toThrow();
    expect(() => click()).not.toThrow();
    // Router 内では navigator を使う（フォールバックしない）
    expect(pushed).toEqual(["/next"]);
    expect(assignSpy).toHaveBeenCalledTimes(1);

    // Router 内 → Router 外
    expect(() => rerender(<Host withRouter={false} />)).not.toThrow();
    expect(() => click()).not.toThrow();
    expect(assignSpy).toHaveBeenCalledTimes(2);
    expect(pushed).toEqual(["/next"]);

    // さらに Router 内へ往復しても壊れない
    expect(() => rerender(<Host withRouter />)).not.toThrow();
    click();
    expect(pushed).toEqual(["/next", "/next"]);
  });

  it("MemoryRouter 内では実際にルートが切り替わる", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <>
                <Probe />
                <LocationView />
              </>
            }
          />
          <Route path="/next" element={<LocationView />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByTestId("path").textContent).toBe("/");
    click();
    expect(screen.getByTestId("path").textContent).toBe("/next");
  });

  it("空文字を渡すと fallbackPath を使う", () => {
    function EmptyProbe() {
      const navigate = useOptionalNavigate("/fallback");
      return (
        <button type="button" data-testid="empty" onClick={() => navigate("")}>
          遷移
        </button>
      );
    }
    render(<EmptyProbe />);
    act(() => {
      screen.getByTestId("empty").click();
    });
    expect(assignSpy).toHaveBeenCalledWith("/fallback");
  });
});

function LocationView() {
  const location = useLocation();
  return <span data-testid="path">{location.pathname}</span>;
}
