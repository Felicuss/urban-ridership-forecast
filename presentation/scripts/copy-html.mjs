// Сборка кладёт страницу в dist/index.html; презентация - один файл chaspik.html рядом с исходниками.
import { copyFileSync, statSync } from 'node:fs';

copyFileSync('dist/index.html', 'chaspik.html');
console.log(`chaspik.html: ${(statSync('chaspik.html').size / 1024).toFixed(0)} КБ`);
