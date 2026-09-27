/**
 * PostCSS 設定。
 *
 * package.json が "type": "module" のため、このファイルも ESM として扱われる。
 * export default でプラグインを渡すこと（module.exports は使えない）。
 */
export default {
    plugins: {
        tailwindcss: {},
        autoprefixer: {},
    },
};
