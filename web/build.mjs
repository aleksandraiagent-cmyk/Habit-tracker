// Сборка app/index.html из артефакта web/src/habit-tracker.html:
//   JSX (<script type="text/babel">) -> обычный JS (esbuild, React внутри),
//   классы Tailwind -> готовый CSS (tailwindcss CLI).
// Результат работает без интернета и без Babel в браузере.
import { build } from 'esbuild';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, 'src', 'habit-tracker.html');
const outDir = join(here, '..', 'app');
const tmp = join(here, '.tmp');
mkdirSync(tmp, { recursive: true });
mkdirSync(outDir, { recursive: true });

const html = readFileSync(src, 'utf8');
const jsx = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)?.[1];
const css = html.match(/<style>([\s\S]*?)<\/style>/)?.[1];
const bodyClass = html.match(/<body class="([^"]*)"/)?.[1];
const title = html.match(/<title>([^<]*)<\/title>/)?.[1] || 'Трекер привычек';
if (!jsx || css == null || !bodyClass) throw new Error('не найден скрипт, стили или <body> в ' + src);

// 1) JS
const entry = join(tmp, 'entry.jsx');
writeFileSync(entry, "import React from 'react';\nimport * as ReactDOM from 'react-dom/client';\n" + jsx);
const res = await build({
  entryPoints: [entry], bundle: true, minify: true, write: false, format: 'iife', target: ['es2019', 'safari13'],
  jsx: 'transform', jsxFactory: 'React.createElement', jsxFragment: 'React.Fragment', charset: 'utf8',
  define: { 'process.env.NODE_ENV': '"production"' }, logLevel: 'warning', absWorkingDir: here,
});
const js = res.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');

// 2) CSS
writeFileSync(join(tmp, 'in.css'), '@tailwind base;\n@tailwind components;\n@tailwind utilities;\n' + css);
writeFileSync(join(tmp, 'tailwind.config.cjs'), `module.exports = {
  content: [${JSON.stringify(src)}],
  darkMode: 'class',
  theme: { extend: { fontFamily: { sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', '"SF Pro Text"', '"Segoe UI"', 'system-ui', 'sans-serif'] } } },
};`);
const tw = join(here, 'node_modules', 'tailwindcss', 'lib', 'cli.js');
execFileSync(process.execPath, [tw, '-c', join(tmp, 'tailwind.config.cjs'), '-i', join(tmp, 'in.css'), '-o', join(tmp, 'out.css'), '--minify'], { stdio: 'inherit', cwd: here });
const outCss = readFileSync(join(tmp, 'out.css'), 'utf8');

// 3) страница
const page = `<!DOCTYPE html>
<html lang="ru" translate="no">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="google" content="notranslate">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Привычки">
<meta name="theme-color" content="#f5f5f7">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="favicon.ico">
<title>${title}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>${outCss}</style>
</head>
<body class="${bodyClass}">
<div id="root"></div>
<script>${js}</script>
</body>
</html>
`;
writeFileSync(join(outDir, 'index.html'), page);
console.log(`Готово: app/index.html (${Math.round(page.length / 1024)} КБ: JS ${Math.round(js.length / 1024)} КБ, CSS ${Math.round(outCss.length / 1024)} КБ)`);
