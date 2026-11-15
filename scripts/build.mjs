import fs from 'node:fs';
const stories = JSON.parse(fs.readFileSync('content/stories.json', 'utf8'));
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const home = fs.readFileSync('index.html', 'utf8');
const header = home.match(/<body>([\s\S]*?)<main id="main">/)[1].replaceAll('href="#', 'href="index.html#').replace('href="index.html#main"', 'href="#main"');
const head = home.slice(0, home.indexOf('<body>'));
const footer = home.slice(home.indexOf('<footer'));
const page = (title, body) => head.replace(/<title>.*?<\/title>/, `<title>${escape(title)} | Menclave</title>`).replace(/<meta name="description"[^>]+>/, `<meta name="description" content="${escape(title)}. Menclave editorial concept preview.">`) + '<body>' + header + '<main id="main">' + body + '</main>' + footer;
const slugs = new Set();
for (const story of stories) {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(story.slug) || slugs.has(story.slug)) throw Error('Invalid or duplicate slug');
  slugs.add(story.slug);
  if (!story.title || !story.category || !story.sections?.length) throw Error('Incomplete story');
  if (!/^https:\/\/images\.unsplash\.com\//.test(story.image)) throw Error('Unapproved image host');
}
const cards = stories.map(s => `<a class="archive-card" data-category="${escape(s.category)}" href="${s.slug}.html"><img loading="lazy" src="${escape(s.image)}" alt="${escape(s.alt)}"><p class="eyebrow">${escape(s.category)}</p><h2>${escape(s.title)}</h2><p>${escape(s.deck)}</p><small>EDITORIAL CONCEPT · ${s.sections.length} REFLECTIONS</small></a>`).join('');
const categories = [...new Set(stories.map(s => s.category))];
fs.writeFileSync('magazine.html', page('The Magazine', `<section class="paper archive"><p class="eyebrow">THE MAGAZINE / THE WHOLE MAN</p><h1 id="archive-heading" class="archive-heading">The Magazine.</h1><p class="archive-deck">Life. Faith. Purpose. Brotherhood.</p><div class="archive-toolbar"><div><a id="archive-all-stories" class="archive-back" href="magazine.html" hidden>← All stories</a><p id="archive-status" class="archive-count" role="status">${stories.length} stories</p></div></div><div class="archive-grid">${cards}</div><p id="archive-empty" hidden>No stories match. <a href="magazine.html">Explore all stories →</a></p></section>`));
for (const s of stories) fs.writeFileSync(`${s.slug}.html`, page(s.title, `<div class="demo-notice">EDITORIAL CONCEPT: Sample copy for design and publishing development.</div><section class="interview-hero"><img class="interview-hero-image" src="${escape(s.image)}" alt="${escape(s.alt)}"><div class="interview-cover"><p class="eyebrow">${escape(s.category)}</p><h1>${escape(s.title)}</h1><p class="interview-deck">${escape(s.deck)}</p><p class="interview-meta">MENCLAVE · EDITORIAL CONCEPT</p></div></section><article class="reading-column"><a class="back-link" href="magazine.html">← All stories</a>${s.sections.map(p => `<section><h2>${escape(p.heading)}</h2><p>${escape(p.body)}</p></section>`).join('')}<p class="reading-end">LIFE. FAITH. PURPOSE. BROTHERHOOD.</p><a class="back-link" href="magazine.html?category=${encodeURIComponent(s.category)}">Explore ${escape(s.category)} →</a></article>`));
console.log(`Built archive and ${stories.length} story pages.`);
