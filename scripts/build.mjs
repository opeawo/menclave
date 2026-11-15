import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
const rich = JSON.parse(execFileSync('python3',['scripts/render-samples.py'],{encoding:'utf8'}));
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
  if (!story.title || !story.category || !(story.blocks?.length || story.sections?.length)) throw Error('Incomplete story');
  if (!/^https:\/\/images\.unsplash\.com\//.test(story.image) && !/^\/assets\/[a-z0-9-]+\.(?:jpg|png)$/.test(story.image)) throw Error('Unapproved image host');
}
const cards = stories.map(s => `<a class="archive-card" data-category="${escape(s.category)}" href="${s.slug}.html"><img loading="lazy" src="${escape(s.image).replace(/^\/assets\//, "assets/")}" alt="${escape(s.alt)}"><p class="eyebrow">${escape(s.category)}</p><h2>${escape(s.title)}</h2><p>${escape(s.deck)}</p><small>EDITORIAL CONCEPT · ${escape(s.format.replaceAll('-',' ').toUpperCase())}</small></a>`).join('');
const categories = [...new Set(stories.map(s => s.category))];
fs.writeFileSync('magazine.html', page('The Magazine', `<section class="paper archive"><p class="eyebrow">THE MAGAZINE / THE WHOLE MAN</p><h1 id="archive-heading" class="archive-heading">The Magazine.</h1><p class="archive-deck">Life. Faith. Purpose. Brotherhood.</p><div class="archive-toolbar"><div><a id="archive-all-stories" class="archive-back" href="magazine.html" hidden>← All stories</a><p id="archive-status" class="archive-count" role="status">${stories.length} stories</p></div></div><div class="archive-grid">${cards}</div><p id="archive-empty" hidden>No stories match. <a href="magazine.html">Explore all stories →</a></p></section>`));
for (const s of stories) fs.writeFileSync(`${s.slug}.html`, page(s.title, `${["profile","opinion"].includes(s.format) ? "" : '<div class="demo-notice">EDITORIAL CONCEPT: Sample copy for design and publishing development.</div>'}<section class="interview-hero article-hero--${escape(s.hero_layout || "overlay-left")}"><img class="interview-hero-image" src="${escape(s.image).replace(/^\/assets\//, "assets/")}" alt="${escape(s.alt)}"><div class="interview-cover"><p class="eyebrow">${escape(s.category)} · ${escape(s.format.replaceAll('-',' '))}</p><h1>${escape(s.title)}</h1><p class="interview-deck">${escape(s.deck)}</p><p class="interview-meta">${["profile","opinion"].includes(s.format) ? "MENCLAVE" : "MENCLAVE · EDITORIAL CONCEPT"}</p></div></section><article class="editorial-body">${rich[s.slug].replaceAll('href="/conversations/','href="enclave.html?thread=')}<a class="back-link" href="magazine.html">← All stories</a></article>`));
console.log(`Built archive and ${stories.length} story pages.`);
