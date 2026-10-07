// Test XSS vulnerability in mediaAttrs — executes actual app.js code
// Run: node test_xss.js
// Expected: FAIL before fix (quote breakout), PASS after fix

const fs = require('fs');
const path = require('path');

// Load actual app.js and extract the functions
const appJs = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf-8');

// Extract escapeHtml, mediaSrc, mediaAttrs from app.js
const funcMatch = appJs.match(/function escapeHtml[\s\S]*?^}/m);
const mediaSrcMatch = appJs.match(/function mediaSrc[\s\S]*?^}/m);
const mediaAttrsMatch = appJs.match(/function mediaAttrs[\s\S]*?^}/m);

if (!funcMatch || !mediaSrcMatch || !mediaAttrsMatch) {
  console.error('FAIL: could not extract functions from app.js');
  process.exit(1);
}

// Evaluate in isolated context
const escapeHtml = eval(`(${funcMatch[0]})`);
const mediaSrc = eval(`(${mediaSrcMatch[0]})`);
const mediaAttrs = eval(`(${mediaAttrsMatch[0]})`);

// Test cases — all inputs must be safe (no attribute breakout)
const tests = [
  { name: 'normal local', input: { local: 'media/img1.jpg' } },
  { name: 'normal url', input: { url: 'https://example.com/img.jpg' } },
  { name: 'quote in url', input: { url: 'https://example.com/img.jpg" onerror="alert(1)' } },
  { name: 'quote in local', input: { local: 'media/img.jpg" onerror="alert(1)' } },
  { name: 'both with quote', input: { local: 'media/img.jpg" onerror="alert(1)', url: 'https://example.com/img.jpg' } },
];

let failed = 0;
for (const t of tests) {
  const result = mediaAttrs(t.input);
  // All inputs must be safe: no unescaped quote followed by space and attribute name
  const hasBreakout = /[^&]"\s+onerror=/.test(result) || /[^&]"\s+src=/.test(result);
  const passed = !hasBreakout;
  console.log(`${t.name}: ${passed ? 'PASS' : 'FAIL'}`);
  if (!passed) {
    console.log(`  input: ${JSON.stringify(t.input)}`);
    console.log(`  output: ${result}`);
    failed++;
  }
}

console.log(`\n${tests.length - failed}/${tests.length} passed`);
process.exit(failed > 0 ? 1 : 0);
