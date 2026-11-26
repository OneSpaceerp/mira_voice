import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

// vite-plugin-pwa 2.x (Workbox 7.4). injectManifest = we own src/sw.ts.
export default defineConfig({
  plugins: [
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'prompt',          // show "Update available" UI; never yank the page mid-task
      injectRegister: false,           // we register in src/pwa/register.ts
      pwaAssets: { config: true },     // icons + apple-touch-icon from pwa-assets.config.ts
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,svg,png,webp,avif,woff2,ico}'],
        maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
      },
      devOptions: { enabled: true, type: 'module', navigateFallback: 'index.html' },
      manifest: {
        id: '/',
        name: 'Fieldnote — Field Work Companion',
        short_name: 'Fieldnote',
        description: 'Capture site visits, photos and tasks — online or off.',
        lang: 'en',
        dir: 'auto',
        start_url: '/?source=pwa',
        scope: '/',
        display: 'standalone',
        display_override: ['window-controls-overlay', 'standalone'],
        orientation: 'any',
        theme_color: '#0f1720',
        background_color: '#0f1720',
        categories: ['productivity', 'business'],
        launch_handler: { client_mode: ['navigate-existing', 'auto'] },
        icons: [
          { src: 'pwa-64x64.png', sizes: '64x64', type: 'image/png', purpose: 'any' },
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: 'maskable-icon-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
        screenshots: [
          { src: 'screenshots/narrow-1.png', sizes: '1080x1920', type: 'image/png', form_factor: 'narrow', label: 'Today view with tasks and visits' },
          { src: 'screenshots/wide-1.png', sizes: '1920x1080', type: 'image/png', form_factor: 'wide', label: 'Dashboard on desktop' },
        ],
        shortcuts: [
          { name: 'New visit', short_name: 'Visit', url: '/?action=new-visit&source=shortcut',
            icons: [{ src: 'pwa-96x96.png', sizes: '96x96', type: 'image/png' }] },
        ],
        share_target: {
          action: '/share-target',
          method: 'POST',
          enctype: 'multipart/form-data',
          params: { title: 'title', text: 'text', url: 'url', files: [{ name: 'media', accept: ['image/*'] }] },
        },
      },
    }),
  ],
});
