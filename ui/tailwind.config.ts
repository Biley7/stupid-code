import type { Config } from 'tailwindcss';
import plugin from 'tailwindcss/plugin';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    // Full replacement (not `extend`): no default palette color exists.
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      obsidian: 'var(--color-obsidian)',
      surface: 'var(--color-surface)',
      bone: 'var(--color-bone)',
      muted: 'var(--color-muted)',
      hairline: 'var(--color-hairline)',
      crimson: 'var(--color-crimson)',
      signal: 'var(--color-signal)',
      verified: 'var(--color-verified)',
      stale: 'var(--color-stale)',
    },
    fontFamily: {
      sans: ['ui-sans-serif', 'system-ui', 'sans-serif'],
      mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
    },
  },
  plugins: [
    plugin(({ addVariant }) => {
      addVariant('autopsy', '[data-visual-mode="autopsy"] &');
      addVariant('lab', '[data-visual-mode="lab"] &');
    }),
  ],
};

export default config;
