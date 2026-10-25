import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// No instance value enters the build: the API origin is read from
// /config.json when the page starts (src/config.ts), and the container
// renders that file from its environment when it starts.
export default defineConfig({
  plugins: [vue()],
  build: { target: 'es2022', sourcemap: false },
})
