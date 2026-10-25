const fs = require('fs');
const path = require('path');

const htmlPath = path.join(__dirname, '..', 'frontend', 'dashboard.html');
const jsPath = path.join(__dirname, '..', 'frontend', 'js', 'dashboard.js');

const html = fs.readFileSync(htmlPath, 'utf8');
const js = fs.readFileSync(jsPath, 'utf8');

// Find all document.getElementById('...') in dashboard.js
const idRegex = /document\.getElementById\(['"]([^'"]+)['"]\)/g;
let match;
const checkedIds = new Set();
const missingIds = [];

while ((match = idRegex.exec(js)) !== null) {
  const id = match[1];
  if (!checkedIds.has(id)) {
    checkedIds.add(id);
    const idInHtmlRegex = new RegExp(`id=["']${id}["']`);
    if (!idInHtmlRegex.test(html)) {
      missingIds.push(id);
    }
  }
}

console.log('Total unique IDs checked:', checkedIds.size);
console.log('Missing IDs in HTML:', missingIds);

if (missingIds.length > 0) {
  console.log('Reviewing if any missing IDs are accessed without null checks...');
  missingIds.forEach((id) => {
    // Check how it's used in js
    const usageRegex = new RegExp(`document\\.getElementById\\(['"]${id}['"]\\)\\.`, 'g');
    if (usageRegex.test(js)) {
      console.error(`DANGER: Direct property access on missing element id "${id}"!`);
    } else {
      console.log(`Safe: id "${id}" is either null-checked or optional.`);
    }
  });
} else {
  console.log('>>> ALL REFERENCED IDs EXIST IN HTML! <<<');
}
