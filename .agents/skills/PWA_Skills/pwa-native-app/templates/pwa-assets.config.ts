import { defineConfig, minimal2023Preset } from '@vite-pwa/assets-generator/config';

// One square SVG/PNG in, every icon out (pwa-64/192/512, maskable-512, apple-touch-icon-180, favicon.ico).
export default defineConfig({
  headLinkOptions: { preset: '2023' },
  preset: {
    ...minimal2023Preset,
    transparent: { ...minimal2023Preset.transparent, sizes: [64, 96, 192, 512] }, // 96 = shortcut icon size
    maskable: { ...minimal2023Preset.maskable, padding: 0.3, resizeOptions: { background: '#0f1720' } },
    apple: { ...minimal2023Preset.apple, padding: 0.3, resizeOptions: { background: '#0f1720' } },
  },
  images: ['public/logo.svg'],
});
