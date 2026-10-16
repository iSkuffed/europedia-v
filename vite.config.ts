import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'

// relative base: the built site works from any GitHub Pages subpath
export default defineConfig({
  base: './',
  plugins: [svelte()],
})
