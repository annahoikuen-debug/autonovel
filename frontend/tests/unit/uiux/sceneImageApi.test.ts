/**
 * R1 の回帰テスト：シーン画像 API が **実在する** 契約で叩かれること。
 *
 * 以前はバックエンドに存在しない `/api/multimedia/images/{scene}` を叩いていた。
 * ここは「実在する `/images/{book_id}/{scene_name}`」を叩く契約と、
 * 旧パス（存在しない）を叩かないことを固定する回帰テスト。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  fetchSceneIllustration,
  type SceneIllustrationLookup,
} from "../../../src/api/illustrations";
import { apiFetch } from "../../../src/api/client";

vi.mock("../../../src/api/client", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

function respond(data: unknown, ok = true) {
  return { ok, json: async () => data } as unknown as Response;
}

beforeEach(() => {
  mockedApiFetch.mockReset();
});

describe("R1: シーン画像 API", () => {
  it("実在するパス /images/{book_id}/{scene} を叩く", async () => {
    mockedApiFetch.mockResolvedValue(
      respond({ found: true, image_url: "https://img/x.png", illustration_id: 7 }),
    );

    await fetchSceneIllustration(42, "夕暮れの街");

    expect(mockedApiFetch).toHaveBeenCalledWith("/images/42/%E5%A4%95%E6%9A%AE%E3%82%8C%E3%81%AE%E8%A1%97");
  });

  it("挿絵があれば image_url を返す", async () => {
    const payload: SceneIllustrationLookup = {
      found: true,
      image_url: "https://img/scene.png",
      illustration_id: 12,
    };
    mockedApiFetch.mockResolvedValue(respond(payload));

    await expect(fetchSceneIllustration(1, "シーンA")).resolves.toBe("https://img/scene.png");
  });

  it("found=false（未生成）なら例外ではなく undefined を返す", async () => {
    mockedApiFetch.mockResolvedValue(
      respond({ found: false, image_url: null, illustration_id: null }),
    );

    await expect(fetchSceneIllustration(1, "シーンA")).resolves.toBeUndefined();
  });

  it("404 でも例外にせず undefined（未生成と障害を混同しない）", async () => {
    mockedApiFetch.mockResolvedValue(respond({}, false));

    await expect(fetchSceneIllustration(1, "シーンA")).resolves.toBeUndefined();
  });

  it("bookId / sceneName が空なら通信しない", async () => {
    await expect(fetchSceneIllustration(0, "シーンA")).resolves.toBeUndefined();
    await expect(fetchSceneIllustration(1, "")).resolves.toBeUndefined();
    expect(mockedApiFetch).not.toHaveBeenCalled();
  });

  it("存在しない旧パス /api/multimedia/images は呼ばない", async () => {
    mockedApiFetch.mockResolvedValue(
      respond({ found: false, image_url: null, illustration_id: null }),
    );

    await fetchSceneIllustration(1, "シーンA");

    const calledPath = mockedApiFetch.mock.calls[0][0];
    expect(String(calledPath)).not.toContain("/api/multimedia/images");
  });
});
