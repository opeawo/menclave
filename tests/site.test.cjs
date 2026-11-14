const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('homepage and interview exist', () => {
  for (const page of ['index.html', 'interview.html']) {
    const html = fs.readFileSync(page, 'utf8');
    assert.match(html, /<html lang="en">/);
    assert.match(html, /<main id="main">/);
    assert.match(html, /<meta name="viewport"/);
    assert.match(html, /styles.css/);
    assert.match(html, /script.js/);
    assert.match(html, /</html>/);
  }
});

test('every local page link points to a committed page or a section', () => {
  for (const page of ['index.html', 'interview.html']) {
    const html = fs.readFileSync(page, 'utf8');
    const links = [...html.matchAll(/href="([^"]+)"/g)].map(match => match[1]);
    for (const link of links) {
      if (/^(https?:|mailto:|#)/.test(link)) continue;
      const [file, anchor] = link.split('#');
      if (file) assert.ok(fs.existsSync(file), `Missing local file: ${file}`);
      if (anchor) {
        const target = file || page;
        const targetHtml = fs.readFileSync(target, 'utf8');
        assert.ok(targetHtml.includes(`id="${anchor}"`), `Missing #${anchor} on ${target}`);
      }
    }
  }
});

test('prototype must not claim newsletter registration works', () => {
  const script = fs.readFileSync('script.js', 'utf8');
  assert.match(script, /No email has been stored/);
});

test('demo interview is disclosed as fictional', () => {
  const html = fs.readFileSync('interview.html', 'utf8');
  assert.match(html, /fictional/i);
});