/**
 * Tailwind CSS 設定。
 *
 * package.json が "type": "module" のため、このファイルも ESM として扱われる。
 * export default で設定を渡すこと（module.exports は使えない）。
 *
 * `corePlugins.preflight: false` にして、既存の 1600 行超のカスタム CSS
 * （.btn / .input / .card / .studio-pane など）のリセットを壊さないようにする。
 */
export default {
    content: [
        "./src/**/*.{ts,tsx,js,jsx}",
        "./index.html",
    ],
    theme: {
        extend: {
            animation: {
                "fade-in": "fadeIn 0.5s ease-in-out",
                "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
                "spin-slow": "spin 3s linear infinite",
                "slide-up": "slideUp 0.3s ease-out",
                "wizard-fade-in": "wizard-fade-in 0.3s ease-in-out",
                "overlay-fade-in": "overlay-fade-in 0.2s ease-in-out",
            },
            keyframes: {
                fadeIn: {
                    "0%": { opacity: "0" },
                    "100%": { opacity: "1" },
                },
                pulse: {
                    "0%, 100%": { opacity: "1" },
                    "50%": { opacity: "0.5" },
                },
                spin: {
                    "0%": { transform: "rotate(0deg)" },
                    "100%": { transform: "rotate(360deg)" },
                },
                slideUp: {
                    "0%": { transform: "translateY(20px)", opacity: "0" },
                    "100%": { transform: "translateY(0)", opacity: "1" },
                },
                "wizard-fade-in": {
                    "0%": { opacity: "0", transform: "translateY(10px)" },
                    "100%": { opacity: "1", transform: "translateY(0)" },
                },
                "overlay-fade-in": {
                    "0%": { opacity: "0" },
                    "100%": { opacity: "1" },
                },
            },
        },
    },
    // 既存 BEM CSS のリセットを壊さない
    corePlugins: {
        preflight: false,
    },
};
