import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // This forces third-party libraries like lucide-react to use the root React instances
    dedupe: ['react', 'react-dom'],
  },
});
