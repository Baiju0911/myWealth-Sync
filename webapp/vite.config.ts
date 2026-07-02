import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    // This forces third-party libraries like lucide-react to use the root React instances
    dedupe: ['react', 'react-dom'],
  },
});
