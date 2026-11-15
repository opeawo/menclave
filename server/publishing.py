"""Public rendering reads the same database records managed by MCP."""
import html
import json
import re
from urllib.parse import quote
from xml.etree.ElementTree import Element,SubElement,tostring
from flask import render_template_string,request
from server.app import ROOT
from server.services import canonical

BASE='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{{description}}">{% if noindex %}<meta name="robots" content="noindex">{% endif %}<link rel="canonical" href="{{canonical_url}}"><title>{{title}} | {{brand.title}}</title><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800;900&family=IBM+Plex+Sans:wght@400;500;600;700&family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&display=swap"><link rel="stylesheet" href="/styles.css"></head><body><a class="skip" href="#main">Skip to content</a><header class="site-header"><a class="wordmark" href="/">{{brand.title|upper}} <span>/</span></a><span class="brand-tag">THE ART OF<br>BEING A MAN.</span><form class="global-search" role="search" action="/search" method="get"><label class="sr-only" for="global-query">Search articles and conversations</label><span class="search-glyph" aria-hidden="true"></span><input id="global-query" type="search" name="q" maxlength="200" placeholder="Search Menclave" autocomplete="off"><button type="submit" aria-label="Search Menclave">Search</button></form><nav class="desktop-nav" aria-label="Primary">{% for link in navigation %}<a href="{{link.href}}">{{link.label}}</a>{% endfor %}</nav><button class="menu-toggle" aria-label="Open navigation" aria-expanded="false" aria-controls="mobile-nav"><span></span><span></span><span></span></button></header><nav class="mobile-nav" id="mobile-nav" aria-label="Mobile" hidden>{% for link in navigation %}<a href="{{link.href}}">{{link.label}}</a>{% endfor %}</nav><main id="main">{{body|safe}}</main><footer class="site-footer"><strong>MENCLAVE /</strong><p>The Art of Being a Man.</p><a href="/enclave.html">The Enclave</a></footer><script defer src="/script.js"></script></body></html>'''

def bootstrap(platform):
    with platform.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM config WHERE key='editorial_imported'").fetchone():return
        for item in json.loads((ROOT/'content/stories.json').read_text()):
            data=dict(item);data['concept']=True
            platform.save(db,'bootstrap','article',data,status='published')
        db.execute("INSERT INTO config VALUES('editorial_imported','1')")

def shell(platform,title,description,body,**values):
    with platform.store.connect() as db:
        row=db.execute("SELECT data FROM entities WHERE id='navigation'").fetchone()
        site=db.execute("SELECT data FROM entities WHERE id='site'").fetchone()
        brand={'title':'Menclave',**(json.loads(site[0]) if site else {})}
        navigation=json.loads(row[0]).get('links',[]) if row else [{'href':'/magazine','label':'Magazine'},{'href':'/enclave.html','label':'The Enclave'},{'href':'/#newsletter','label':'Newsletter'}]
    return render_template_string(BASE.replace('</head>','<link rel="stylesheet" href="/theme.css"></head>'),title=title,description=description,navigation=navigation,brand=brand,noindex=bool(values.get('story',{}).get('noindex') or values.get('story',{}).get('concept')),canonical_url=__import__('os').environ.get('ENCLAVE_ORIGIN',request.host_url.rstrip('/'))+(values.get('story',{}).get('canonical') or request.path),body=render_template_string(body,**values))

def archive(platform):
    query=request.args.get('q','')[:200];category=request.args.get('category','')
    with platform.store.connect() as db:
        rows=db.execute('SELECT snapshot FROM published_content').fetchall()
        stories=[json.loads(row[0]) for row in rows]
        stories=[v for v in stories if v['kind']!='newsletter' and (not query or query.lower() in canonical(v['data']).lower()) and (not category or v['data'].get('category')==category)]
        stories=sorted(stories,key=lambda v:v['updated'],reverse=True)[:100]
    heading=category or 'The Magazine.'
    return shell(platform,heading,'Life. Faith. Purpose. Brotherhood.','''<section class="paper archive"><p class="eyebrow">THE MAGAZINE / THE WHOLE MAN</p><h1 class="archive-heading">{{heading}}</h1><p class="archive-deck">{% if category %}Perspective, practice and stories for a life well lived.{% else %}Life. Faith. Purpose. Brotherhood.{% endif %}</p><div class="archive-toolbar"><div>{% if category or q %}<a class="archive-back" href="/magazine">← All stories</a>{% endif %}<p class="archive-count">{{stories|length}} {{'story' if stories|length==1 else 'stories'}}{% if q %} matching “{{q}}”{% endif %}</p></div></div><div class="archive-grid">{% for story in stories %}<a class="archive-card" href="/magazine/{{story.data.slug}}">{% if story.data.image %}<img loading="lazy" src="{{story.data.image}}" alt="{{story.data.alt}}">{% endif %}<p class="eyebrow">{{story.data.category}}</p><h2>{{story.data.title}}</h2><p>{{story.data.deck}}</p>{% if story.data.concept %}<small>EDITORIAL CONCEPT</small>{% endif %}</a>{% else %}<p>No published stories match. <a class="back-link" href="/magazine">Explore all stories →</a></p>{% endfor %}</div></section>''',stories=stories,q=query,category=category,heading=heading)

def article(platform,slug):
    with platform.store.connect() as db:
        row=db.execute("SELECT p.snapshot FROM published_content p JOIN entities e ON e.id=p.entity WHERE json_extract(p.snapshot,'$.data.slug')=?",(slug,)).fetchone()
        if not row:
            known=db.execute("SELECT 1 FROM entities WHERE json_extract(data,'$.slug')=? AND kind IN ('article','interview','news','page','newsletter')",(slug,)).fetchone()
            return ('',404) if known else (None,None)
        item=json.loads(row[0])
        if item['data'].get('author_id'):
            author=db.execute("SELECT data FROM entities WHERE id=? AND kind='author'",(item['data']['author_id'],)).fetchone()
            if author:item['data']['byline']=json.loads(author[0]).get('name','')
        if item['data'].get('media_id'):
            media=db.execute("SELECT data FROM entities WHERE id=? AND kind='media' AND status!='archived'",(item['data']['media_id'],)).fetchone()
            if media:item['data']['image']=json.loads(media[0])['path']
    data=item['data']
    return shell(platform,data.get('seo_title') or data['title'],data.get('seo_description') or data.get('deck',''),'''{% if story.concept %}<div class="demo-notice">EDITORIAL CONCEPT: sample copy, not published reporting.</div>{% endif %}<section class="interview-hero">{% if story.image %}<img class="interview-hero-image" src="{{story.image}}" alt="{{story.alt}}">{% endif %}<div class="interview-cover"><p class="eyebrow">{{story.category}}</p><h1>{{story.title}}</h1><p class="interview-deck">{{story.deck}}</p>{% if story.byline %}<p class="interview-meta">By {{story.byline}}</p>{% endif %}</div></section><article class="reading-column">{% for section in story.sections %}<section><h2>{{section.heading}}</h2><p>{{section.body}}</p></section>{% endfor %}<a href="/magazine" class="back-link">← All stories</a></article>''',story=data),200

def home(platform):
    source=(ROOT/'index.html').read_text()
    with platform.store.connect() as db:
        row=db.execute("SELECT data FROM entities WHERE id='homepage'").fetchone()
        config=json.loads(row[0]) if row else {}
        if config.get('hero_id'):
            hero=db.execute('SELECT snapshot FROM published_content WHERE entity=?',(config['hero_id'],)).fetchone()
            if hero:
                data=json.loads(hero[0])['data'];source=re.sub(r'(<div class="hero-copy">[\s\S]*?<h1>)[\s\S]*?</h1>',lambda m:m[1]+html.escape(data['title'])+'</h1>',source,count=1)
                source=re.sub(r'(<p class="hero-deck">)[\s\S]*?</p>',lambda m:m[1]+html.escape(data.get('deck',''))+'</p>',source,count=1)
                source=source.replace('href="good-man.html"','href="/magazine/'+quote(data['slug'])+'"',1)
        if config.get('featured_ids'):
            cards=[]
            for id in config['featured_ids']:
                row=db.execute('SELECT snapshot FROM published_content WHERE entity=?',(id,)).fetchone()
                if row:
                    story=json.loads(row[0])['data'];cards.append('<a class="archive-card" href="/magazine/'+quote(story['slug'])+'"><p class="eyebrow">'+html.escape(story.get('category',''))+'</p><h2>'+html.escape(story['title'])+'</h2><p>'+html.escape(story.get('deck',''))+'</p></a>')
            marker=source.find('<div class="latest-grid">')
            end=source.find('</section>',marker)
            if marker>=0 and end>=0:source=source[:marker]+'<div class="archive-grid">'+''.join(cards)+'</div>'+source[end:]
        if config.get('heading'):source=source.replace('THE LATEST',html.escape(config['heading']))
        navigation=db.execute("SELECT data FROM entities WHERE id='navigation'").fetchone()
        if navigation:
            links=json.loads(navigation[0]).get('links',[]);markup=''.join('<a href="'+html.escape(link['href'],quote=True)+'">'+html.escape(link['label'])+'</a>' for link in links)
            source=re.sub(r'(<nav class="desktop-nav"[^>]*>)[\s\S]*?</nav>',lambda m:m[1]+markup+'</nav>',source,count=1)
            source=re.sub(r'(<nav class="mobile-nav"[^>]*>)[\s\S]*?</nav>',lambda m:m[1]+markup+'</nav>',source,count=1)
        site=db.execute("SELECT data FROM entities WHERE id='site'").fetchone()
        if site:
            data=json.loads(site[0]);source=source.replace('<title>Menclave | The Art of Being a Man</title>','<title>'+html.escape(data.get('title','Menclave'))+' | '+html.escape(data.get('tagline','The Art of Being a Man'))+'</title>');source=source.replace('The Art of Being a Man.',html.escape(data.get('tagline','The Art of Being a Man.')))
    source=source.replace('</head>','<link rel="stylesheet" href="/theme.css"></head>')
    return source

def feed(platform,rss=False):
    base=request.host_url.rstrip('/')
    with platform.store.connect() as db:stories=[json.loads(r[0]) for r in db.execute('SELECT snapshot FROM published_content LIMIT 1000').fetchall()]
    if rss:
        root=Element('rss',version='2.0');channel=SubElement(root,'channel')
        for tag,text in [('title','Menclave'),('link',base),('description','The Art of Being a Man')]:SubElement(channel,tag).text=text
        for story in stories:
            item=SubElement(channel,'item')
            for tag,text in [('title',('[Editorial concept] ' if story['data'].get('concept') else '')+story['data']['title']),('link',base+'/magazine/'+story['data']['slug']),('description',story['data'].get('deck','')),('guid',story['id'])]:SubElement(item,tag).text=text
    else:
        root=Element('urlset',xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
        for story in stories:
            if story['data'].get('concept') or story['data'].get('noindex'):continue
            SubElement(SubElement(root,'url'),'loc').text=base+'/magazine/'+story['data']['slug']
    return tostring(root,encoding='utf-8',xml_declaration=True)

def unified_search(platform):
    query=request.args.get('q','').strip()[:200]
    scope=request.args.get('type','all')
    if scope not in {'all','articles','conversations'}:scope='all'
    articles=[];conversations=[]
    if query:
        with platform.store.connect() as db:
            for row in db.execute('SELECT snapshot FROM published_content').fetchall():
                item=json.loads(row[0]);data=item['data']
                if item['kind']=='newsletter':continue
                text=' '.join([data.get('title',''),data.get('deck',''),data.get('category','')]+[str(section.get(k,'')) for section in data.get('sections',[]) for k in ['heading','body']])
                if query.casefold() in text.casefold():
                    articles.append({'kind':item['kind'],'title':data['title'],'excerpt':data.get('deck','')[:220],'category':data.get('category',''),'url':'/magazine/'+data['slug'],'concept':data.get('concept',False)})
            rows=db.execute("SELECT p.id,p.title,p.body,p.topic,p.created,(SELECT count(*) FROM posts r WHERE r.parent=p.id AND r.status='approved') replies FROM posts p WHERE p.parent IS NULL AND p.status='approved' AND (instr(lower(p.title || ' ' || p.body || ' ' || p.topic),lower(?))>0 OR EXISTS (SELECT 1 FROM posts r WHERE r.parent=p.id AND r.status='approved' AND instr(lower(r.body),lower(?))>0)) ORDER BY p.created DESC,p.id LIMIT 101",(query,query)).fetchall()
            conversations=[{'title':r['title'],'excerpt':r['body'][:220],'topic':r['topic'],'replies':r['replies'],'url':'/enclave.html?thread='+r['id']} for r in rows]
    return shell(platform,'Search Menclave','Articles and honest conversations, in one place.','''<section class="site-search-page"><p class="eyebrow">EXPLORE MENCLAVE</p><h1>{% if q %}Results for “{{q}}”{% else %}A little perspective starts here.{% endif %}</h1><p class="search-intro">Articles and Enclave conversations. One search.</p><nav class="search-tabs" aria-label="Search results"><a href="/search?q={{q|urlencode}}" {% if scope=='all' %}aria-current="page"{% endif %}>All <span>{{articles|length + conversations|length}}</span></a><a href="/search?q={{q|urlencode}}&amp;type=articles" {% if scope=='articles' %}aria-current="page"{% endif %}>Articles <span>{{articles|length}}</span></a><a href="/search?q={{q|urlencode}}&amp;type=conversations" {% if scope=='conversations' %}aria-current="page"{% endif %}>Conversations <span>{{conversations|length}}</span></a></nav>{% if not q %}<div class="search-empty"><h2>What’s on your mind?</h2><p>Use the search bar above to explore faith, family, ambition and everything in between.</p><a href="/magazine">Explore the magazine →</a></div>{% else %}{% if scope in ['all','articles'] and articles %}<section aria-labelledby="article-results"><h2 id="article-results">From the magazine</h2>{% for item in articles[:30] %}<a class="unified-result" href="{{item.url}}"><span class="result-type">{{item.kind|capitalize}} · {{item.category}}</span><h3>{{item.title}}</h3><p>{{item.excerpt}}</p>{% if item.concept %}<small>Editorial concept</small>{% endif %}</a>{% endfor %}</section>{% endif %}{% if scope in ['all','conversations'] and conversations %}<section aria-labelledby="conversation-results"><h2 id="conversation-results">From The Enclave</h2>{% for item in conversations[:30] %}<a class="unified-result" href="{{item.url}}"><span class="result-type">Conversation · {{item.topic}}</span><h3>{{item.title}}</h3><p>{{item.excerpt}}</p><small>{{item.replies}} {{'reply' if item.replies==1 else 'replies'}}</small></a>{% endfor %}</section>{% endif %}{% if scope=='articles' and not articles or scope=='conversations' and not conversations or not articles and not conversations %}<div class="search-empty"><h2>No matches yet.</h2><p>Try a shorter phrase or another topic in the search bar above.</p></div>{% endif %}{% if articles|length>30 or conversations|length>30 %}<p class="form-hint">Showing up to 30 results per section. Refine your search to see more.</p>{% endif %}{% endif %}</section>''',q=query,scope=scope,articles=articles,conversations=conversations)
