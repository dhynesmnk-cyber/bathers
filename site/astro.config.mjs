import { defineConfig } from "astro/config";
import mdx from "@astrojs/mdx";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  site: "https://bathers-directory.netlify.app",
  output: "static",
  integrations: [mdx()],
  vite: {
    plugins: [tailwindcss()],
  },
});
