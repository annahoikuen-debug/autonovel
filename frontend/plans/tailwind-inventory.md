# Tailwind CSS Class Inventory

Extracted from `src/**/*.tsx` files. Total unique class strings: 683.

## Observation

Many of the extracted class strings are **not** single Tailwind utilities but rather:
- Complete Tailwind utility strings (e.g., `flex items-center gap-2`)
- BEM-like custom class names (e.g., `asset-pack-panel__header`)
- Hybrid strings that mix Tailwind utilities with custom names (e.g., `btn btn-primary asset-pack-panel__btn-generate`)
- Dynamic class names that are constructed via template literals (not fully captured in this static extraction)

For Tailwind to work, we need to ensure that:
1. The Tailwind configuration scans all `.tsx` files.
2. We do not break existing styling by introducing Tailwind's preflight (reset) if it conflicts with our custom base styles.
3. We can keep our existing BEM-like class names for component scoping and use Tailwind utilities for layout and styling.

## Next Steps

1. Add Tailwind and PostCSS as dev dependencies.
2. Create `tailwind.config.js` with content pointing to `./src/**/*.{ts,tsx}`.
3. Create `postcss.config.js` to use Tailwind and Autoprefixer.
4. Add `@tailwind base; @tailwind components; @tailwind utilities;` to `src/index.css` (or a dedicated CSS file) while being cautious of the order.
5. Optionally disable Tailwind's preflight if it conflicts with our existing reset (see `index.css` lines 46-50).
6. After setup, we can start replacing custom CSS with Tailwind utilities where appropriate, but we can also keep the existing class names and just add Tailwind utilities alongside.

## Sample of Extracted Class Strings (first 200)