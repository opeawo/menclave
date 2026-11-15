"""Public rendering reads the same database records managed by MCP."""
import html
import os
import time
from server.editorial import render_blocks, blocks_text
import json
import re
from urllib.parse import quote
from xml.etree.ElementTree import Element,SubElement,tostring
from flask import render_template_string,request
from server.app import ROOT
from server.services import canonical

BASE='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{{description}}"><meta property="og:title" content="{{title}}"><meta property="og:description" content="{{description}}"><meta property="og:type" content="article"><meta property="og:url" content="{{canonical_url}}">{% if noindex %}<meta name="robots" content="noindex">{% endif %}<link rel="canonical" href="{{canonical_url}}"><title>{{title}} | {{brand.title}}</title><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800;900&family=IBM+Plex+Sans:wght@400;500;600;700&family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&display=swap"><link rel="stylesheet" href="/styles.css"></head><body><a class="skip" href="#main">Skip to content</a><header class="site-header"><a class="wordmark" href="/">{{brand.title|upper}} <span>/</span></a><span class="brand-tag">THE ART OF<br>BEING A MAN.</span><form class="global-search" role="search" action="/search" method="get"><label class="sr-only" for="global-query">Search articles and conversations</label><span class="search-glyph" aria-hidden="true"></span><input id="global-query" type="search" name="q" maxlength="200" placeholder="Search Menclave" autocomplete="off"><button type="submit" aria-label="Search Menclave">Search</button></form><nav class="desktop-nav" aria-label="Primary">{% for link in navigation %}<a href="{{link.href}}">{{link.label}}</a>{% endfor %}</nav><button class="menu-toggle" aria-label="Open navigation" aria-expanded="false" aria-controls="mobile-nav"><span></span><span></span><span></span></button></header><nav class="mobile-nav" id="mobile-nav" aria-label="Mobile" hidden>{% for link in navigation %}<a href="{{link.href}}">{{link.label}}</a>{% endfor %}</nav><main id="main">{{body|safe}}</main><footer class="site-footer"><strong>MENCLAVE /</strong><p>The Art of Being a Man.</p><a href="/conversations">Conversations</a></footer><script defer src="/script.js"></script></body></html>'''

def bootstrap(platform):
    with platform.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        first=not db.execute("SELECT 1 FROM config WHERE key='editorial_imported'").fetchone()
        upgrade=not db.execute("SELECT 1 FROM config WHERE key='sample_formats_v2'").fetchone()
        if first or upgrade:
            for source in json.loads((ROOT/'content/stories.json').read_text()):
                data=dict(source);data['concept']=True
                row=db.execute("SELECT * FROM entities WHERE json_extract(data,'$.slug')=?",(data['slug'],)).fetchone()
                if not row and first or not row and data['slug'] in {'ibidapo-lawal','jensen-huang'}:
                    platform.save(db,'bootstrap','article',data,status='published')
                elif row and upgrade and row['status']=='published':
                    actor=db.execute('SELECT actor FROM entity_revisions WHERE entity=? AND revision=?',(row['id'],row['revision'])).fetchone()
                    if actor and actor[0] in {'bootstrap','bootstrap-formats'}:platform.save(db,'bootstrap-formats','article',data,row['id'],row['revision'],'published')
            db.execute("INSERT OR IGNORE INTO config VALUES('editorial_imported','1')")
            db.execute("INSERT OR IGNORE INTO config VALUES('sample_formats_v2','1')")
        if os.environ.get('MENCLAVE_SAMPLE_THREADS','1')=='1' and not db.execute("SELECT 1 FROM config WHERE key='sample_threads_v1'").fetchone():
            topic='Culture & Society';stamp=int(time.time())
            samples=[('sample-listening',None,'How do you listen when you already disagree?','Fictional example: I keep planning my answer before the other person finishes. What helps you slow down when a conversation gets uncomfortable?'),('sample-listening-1','sample-listening','','Fictional reply: I try repeating what I heard before offering my view. If they say I missed it, I ask them to help me understand.'),('sample-listening-2','sample-listening','','Fictional reply: Sometimes I need a pause. I say I want to return to the conversation after a walk, then agree a time so it does not feel like disappearing.'),('sample-listening-3','sample-listening','','Fictional reply: Understanding is not the same as agreement. I can ask a curious question and still hold a boundary when someone is disrespectful.')]
            for n,(id,parent,title,body) in enumerate(samples):
                db.execute("INSERT INTO posts VALUES(?,?,?,?,?,?,?,?)",(id,parent,topic,title,body,'sample-fixture','approved',stamp+n))
                db.execute('INSERT INTO thread_controls(post,locked,staff,sample) VALUES(?,1,0,1)',(id,))
            db.execute("INSERT INTO config VALUES('sample_threads_v1','1')")

        if os.environ.get('MENCLAVE_SAMPLE_THREADS','1')=='1' and not db.execute("SELECT 1 FROM config WHERE key='sample_vasectomy_v1'").fetchone():
            stamp=int(time.time());topic='Health & Fitness'
            samples=[('sample-vasectomy',None,'My wife wants me to get a vasectomy. Why am I finding it so hard to talk about?',"My wife is asking me to consider a vasectomy because she says the pill is affecting how she feels and she is tired of carrying contraception on her own. I want to take that seriously. But I only know two men who have openly said they have had one. Maybe more have and just never mention it.\n\nPart of me is worried about the procedure. Part of me wonders how I would feel if our circumstances changed. And, if I am honest, part of it is the awkwardness of talking about it at all.\n\nHow did you and your partner talk through the decision? What did you ask a clinician? And why does this still feel like something men are supposed to keep quiet about?"),('sample-vasectomy-1','sample-vasectomy','',"I would separate the decision about more children from the fear of talking about the procedure. Those are two different conversations. Being able to name which one is worrying you might help you both hear each other."),('sample-vasectomy-2','sample-vasectomy','',"Her experience with contraception deserves space in the conversation, and so do your questions about a procedure on your body. I would want the decision to feel informed and freely made, rather than a test of whether either partner cares enough."),('sample-vasectomy-3','sample-vasectomy','',"The silence is worth talking about in its own right. Knowing only two people who discuss it is different from knowing only two people who have had it. I would ask what makes this feel tied to masculinity or shame before letting that decide for me."),('sample-vasectomy-4','sample-vasectomy','',"A useful starting point for a clinician conversation: vasectomy is intended to be permanent, and it does not provide immediate contraceptive protection. Follow-up testing and advice about when to stop other contraception matter. Bring your questions about risks, recovery and alternatives. NHS information: https://www.nhs.uk/contraception/methods-of-contraception/vasectomy-male-sterilisation/what-is-it/")]
            for n,(id,parent,title,body) in enumerate(samples):
                db.execute("INSERT INTO posts VALUES(?,?,?,?,?,?,?,?)",(id,parent,topic,title,body,'sample-fixture','approved',stamp+n))
                db.execute('INSERT INTO thread_controls(post,locked,staff,sample) VALUES(?,1,?,1)',(id,1 if n==4 else 0))
            db.execute("INSERT INTO config VALUES('sample_vasectomy_v1','1')")

def shell(platform,title,description,body,**values):
    with platform.store.connect() as db:
        row=db.execute("SELECT data FROM entities WHERE id='navigation'").fetchone()
        site=db.execute("SELECT data FROM entities WHERE id='site'").fetchone()
        brand={'title':'Menclave',**(json.loads(site[0]) if site else {})}
        navigation=json.loads(row[0]).get('links',[]) if row else [{'href':'/magazine','label':'Magazine'},{'href':'/conversations','label':'Conversations'},{'href':'/#newsletter','label':'Newsletter'}]
    return render_template_string(BASE.replace('</head>','<link rel="stylesheet" href="/theme.css"></head>'),title=title,description=description,navigation=navigation,brand=brand,noindex=bool(values.get('story',{}).get('noindex') or values.get('story',{}).get('concept')),canonical_url=(__import__('os').environ.get('ENCLAVE_ORIGIN') or request.host_url.rstrip('/'))+(values.get('story',{}).get('canonical') or request.path),body=render_template_string(body,**values))

def archive(platform):
    query=request.args.get('q','')[:200];category=request.args.get('category','')
    with platform.store.connect() as db:
        rows=db.execute('SELECT snapshot FROM published_content').fetchall()
        stories=[json.loads(row[0]) for row in rows]
        stories=[v for v in stories if v['kind']!='newsletter' and (not query or query.lower() in canonical(v['data']).lower()) and (not category or v['data'].get('category')==category)]
        stories=sorted(stories,key=lambda v:v['updated'],reverse=True)[:100]
    heading=category or 'The Magazine.'
    return shell(platform,heading,'Life. Faith. Purpose. Brotherhood.','''<section class="paper archive"><p class="eyebrow">THE MAGAZINE / THE WHOLE MAN</p><h1 class="archive-heading">{{heading}}</h1><p class="archive-deck">{% if category %}Perspective, practice and stories for a life well lived.{% else %}Life. Faith. Purpose. Brotherhood.{% endif %}</p><div class="archive-toolbar"><div>{% if category or q %}<a class="archive-back" href="/magazine">← All stories</a>{% endif %}<p class="archive-count">{{stories|length}} {{'story' if stories|length==1 else 'stories'}}{% if q %} matching “{{q}}”{% endif %}</p></div></div><div class="archive-grid">{% for story in stories %}<a class="archive-card" href="/magazine/{{story.data.slug}}">{% if story.data.image %}<img loading="lazy" src="{{story.data.image}}" alt="{{story.data.alt}}">{% endif %}<p class="eyebrow">{{story.data.category}}</p><h2>{{story.data.title}}</h2><p>{{story.data.deck}}</p><small>{{story.data.format|default("Feature")|replace("-"," ")|upper}}{% if story.data.concept %} · EDITORIAL CONCEPT{% endif %}</small></a>{% else %}<p>No published stories match. <a class="back-link" href="/magazine">Explore all stories →</a></p>{% endfor %}</div></section>''',stories=stories,q=query,category=category,heading=heading)

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
    return shell(platform,data.get('seo_title') or data['title'],data.get('seo_description') or data.get('deck',''),'''{% if story.concept and story.format not in ["profile","opinion"] %}<div class="demo-notice">EDITORIAL CONCEPT: sample copy, not published reporting.</div>{% endif %}<section class="interview-hero article-hero--{{story.hero_layout|default("overlay-left")}}">{% if story.image %}<img class="interview-hero-image" src="{{story.image}}" alt="{{story.alt}}">{% endif %}<div class="interview-cover"><p class="eyebrow">{{story.category}} · {{story.format|default("Feature")|replace("-"," ")|title}}</p><h1>{{story.title}}</h1><p class="interview-deck">{{story.deck}}</p><p class="interview-meta">{% if story.byline %}By {{story.byline}}{% else %}MENCLAVE{% endif %} · {{read_minutes}} MIN READ</p></div></section><article class="editorial-body">{{rich_body|safe}}<a href="/magazine" class="back-link">← All stories</a></article>''',story=data,rich_body=render_blocks(data),read_minutes=max(1,len(blocks_text(data.get('blocks',[])).split())//200)),200

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
                source=source.replace('href="ibidapo-lawal.html"','href="/magazine/'+quote(data['slug'])+'"',1)
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
    if not rss:
        with platform.store.connect() as db:
            rows=db.execute("SELECT p.id FROM posts p LEFT JOIN thread_controls c ON c.post=p.id WHERE p.parent IS NULL AND p.status='approved' AND COALESCE(c.sample,0)=0 ORDER BY p.created DESC LIMIT 5000").fetchall()
            for row in rows:SubElement(SubElement(root,'url'),'loc').text=base+'/conversations/'+quote(row['id'],safe='')
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
                text=blocks_text(data.get('blocks',[]))+' '+' '.join([data.get('title',''),data.get('deck',''),data.get('category','')]+[str(section.get(k,'')) for section in data.get('sections',[]) for k in ['heading','body']])
                if query.casefold() in text.casefold():
                    articles.append({'kind':item['kind'],'title':data['title'],'excerpt':data.get('deck','')[:220],'category':data.get('category',''),'url':'/magazine/'+data['slug'],'concept':data.get('concept',False)})
            rows=db.execute("SELECT p.id,p.title,p.body,p.topic,p.created,COALESCE((SELECT sample FROM thread_controls WHERE post=p.id),0) sample,(SELECT count(*) FROM posts r WHERE r.parent=p.id AND r.status='approved') replies FROM posts p WHERE p.parent IS NULL AND p.status='approved' AND (instr(lower(p.title || ' ' || p.body || ' ' || p.topic),lower(?))>0 OR EXISTS (SELECT 1 FROM posts r WHERE r.parent=p.id AND r.status='approved' AND instr(lower(r.body),lower(?))>0)) ORDER BY p.created DESC,p.id LIMIT 101",(query,query)).fetchall()
            conversations=[{'sample':bool(r['sample']),'title':r['title'],'excerpt':r['body'][:220],'topic':r['topic'],'replies':r['replies'],'url':'/conversations/'+quote(r['id'],safe='')} for r in rows]
    return shell(platform,'Search Menclave','Articles and honest conversations, in one place.','''<section class="site-search-page"><p class="eyebrow">EXPLORE MENCLAVE</p><h1>{% if q %}Results for “{{q}}”{% else %}A little perspective starts here.{% endif %}</h1><p class="search-intro">Articles and conversations. One search.</p><nav class="search-tabs" aria-label="Search results"><a href="/search?q={{q|urlencode}}" {% if scope=='all' %}aria-current="page"{% endif %}>All <span>{{articles|length + conversations|length}}</span></a><a href="/search?q={{q|urlencode}}&amp;type=articles" {% if scope=='articles' %}aria-current="page"{% endif %}>Articles <span>{{articles|length}}</span></a><a href="/search?q={{q|urlencode}}&amp;type=conversations" {% if scope=='conversations' %}aria-current="page"{% endif %}>Conversations <span>{{conversations|length}}</span></a></nav>{% if not q %}<div class="search-empty"><h2>What’s on your mind?</h2><p>Use the search bar above to explore faith, family, ambition and everything in between.</p><a href="/magazine">Explore the magazine →</a></div>{% else %}{% if scope in ['all','articles'] and articles %}<section aria-labelledby="article-results"><h2 id="article-results">From the magazine</h2>{% for item in articles[:30] %}<a class="unified-result" href="{{item.url}}"><span class="result-type">{{item.kind|capitalize}} · {{item.category}}</span><h3>{{item.title}}</h3><p>{{item.excerpt}}</p>{% if item.concept %}<small>Editorial concept</small>{% endif %}</a>{% endfor %}</section>{% endif %}{% if scope in ['all','conversations'] and conversations %}<section aria-labelledby="conversation-results"><h2 id="conversation-results">Conversations</h2>{% for item in conversations[:30] %}<a class="unified-result" href="{{item.url}}"><span class="result-type">Conversation · {{item.topic}}</span><h3>{{item.title}}</h3><p>{{item.excerpt}}</p><small>{% if item.sample %}Fictional example · {% endif %}{{item.replies}} {{'reply' if item.replies==1 else 'replies'}}</small></a>{% endfor %}</section>{% endif %}{% if scope=='articles' and not articles or scope=='conversations' and not conversations or not articles and not conversations %}<div class="search-empty"><h2>No matches yet.</h2><p>Try a shorter phrase or another topic in the search bar above.</p></div>{% endif %}{% if articles|length>30 or conversations|length>30 %}<p class="form-hint">Showing up to 30 results per section. Refine your search to see more.</p>{% endif %}{% endif %}</section>''',q=query,scope=scope,articles=articles,conversations=conversations)
