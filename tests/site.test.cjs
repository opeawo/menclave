const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('homepage and interview exist', () => {
  for (const page of fs.readdirSync('.').filter(file => file.endsWith('.html'))) {
    const html = fs.readFileSync(page, 'utf8');
    assert.match(html, /<html lang="en">/);
    assert.match(html, /<main id="main"[^>]*>/);
    assert.match(html, /<meta name="viewport"/);
    assert.match(html, /styles.css/);
    assert.match(html, /script.js/);
    assert.match(html, /<\/html>/);
  }
});

test('every local page link points to a committed page or a section', () => {
  for (const page of fs.readdirSync('.').filter(file => file.endsWith('.html'))) {
    const html = fs.readFileSync(page, 'utf8');
    const links = [...html.matchAll(/href="([^"]+)"/g)].map(match => match[1]);
    for (const link of links) {
      if (/^(https?:|mailto:|#)/.test(link)) continue;
      if (['/sign-in','/create-account'].includes(link)) continue; // Backend routes covered by member integration tests.
      const [path, anchor] = link.split('#');
      const file = path.split('?')[0];
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
 test('generated publication matches source content', () => {
  const stories = JSON.parse(fs.readFileSync('content/stories.json', 'utf8'));
  const archive = fs.readFileSync('magazine.html', 'utf8');
  for (const story of stories) {
    assert.ok(archive.includes(`href="${story.slug}.html"`));
    const page = fs.readFileSync(`${story.slug}.html`, 'utf8');
    assert.ok(page.includes(story.title));
    if (!["profile","opinion","ranked-list"].includes(story.format)) assert.match(page, /EDITORIAL CONCEPT/);
    for (const section of story.sections) assert.ok(page.includes(section.heading));
  }
});
