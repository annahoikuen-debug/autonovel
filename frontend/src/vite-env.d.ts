/// <reference types="vite/client" />

/**
 * Vite が注入する環境変数の型定義。
 *
 * `import.meta.env.VITE_*` を tsc が検査できるようにする（三重スラッシュ
 * 参照で `vite/client` の `ImportMetaEnv` を取り込んでいる）。
 */
interface ImportMetaEnv {
  /** LP の本番オリジン（canonical / OGP 用）。未指定時は window.location.origin。 */
  readonly VITE_SITE_URL?: string;
  /** API ベース URL（任意）。 */
  readonly VITE_API_BASE_URL?: string;
  /** GA4 測定 ID（任意）。 */
  readonly VITE_GA4_MEASUREMENT_ID?: string;
  /** Sentry DSN（任意）。 */
  readonly VITE_SENTRY_DSN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
