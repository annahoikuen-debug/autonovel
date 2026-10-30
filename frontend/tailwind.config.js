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
            colors: {
                brand: {
                    dark: '#020617',
                    surface: '#0f172a',
                    surfaceHover: '#1e293b',
                    text: '#f8fafc',
                    textMuted: '#94a3b8',
                    accent: '#22d3ee',
                    accentHover: '#06b6d4',
                    accentSecondary: '#a855f7',
                    accentSecondaryHover: '#9333ea',
                    success: '#34d399',
                    warning: '#fbbf24',
                    error: '#f87171',
                    border: '#334155',
                },
            },
            fontFamily: {
                sans: [
                    'system-ui', '-apple-system', 'BlinkMacSystemFont',
                    '"Segoe UI"', 'Roboto', '"Hiragino Kaku Gothic ProN"',
                    '"Hiragino Sans"', 'Meiryo', 'sans-serif',
                ],
            },
            animation: {
                "fade-in": "fadeIn 0.5s ease-in-out",
                "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
                "spin-slow": "spin 3s linear infinite",
                "slide-up": "slideUp 0.3s ease-out",
                "wizard-fade-in": "wizard-fade-in 0.3s ease-in-out",
                "overlay-fade-in": "overlay-fade-in 0.2s ease-in-out",
                "fade-in-up": "fadeInUp 0.6s ease-out",
                "scale-in": "scaleIn 0.3s ease-out",
                "pulse-glow": "pulseGlow 3s infinite",
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
                fadeInUp: {
                    "0%": { opacity: "0", transform: "translateY(24px)" },
                    "100%": { opacity: "1", transform: "translateY(0)" },
                },
                scaleIn: {
                    "0%": { transform: "scale(0.95)", opacity: "0" },
                    "100%": { transform: "scale(1)", opacity: "1" },
                },
                pulseGlow: {
                    "0%, 100%": { boxShadow: "0 0 0 0 rgb(34 211 238 / 0.4)" },
                    "50%": { boxShadow: "0 0 0 12px rgb(34 211 238 / 0)" },
                },
            },
        },
    },
    // 既存 BEM CSS のリセットを壊さない
    corePlugins: {
        preflight: false,
    },
};
