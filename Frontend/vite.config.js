import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
// base './' so the build works from any folder or GitHub Pages sub-path (assets are fetched relative to the page).
export default defineConfig({ base: './', plugins: [react()], build: { chunkSizeWarningLimit: 1500 } });
