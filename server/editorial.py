"""Safe, portable editorial blocks shared by live pages and static builds."""
import html
import re
from urllib.parse import urlsplit

TEXT={'type':'string','maxLength':30000}
SHORT={'type':'string','maxLength':1000}
IMAGE={'type':'object','properties':{'src':SHORT,'alt':SHORT,'caption':SHORT},'required':['src','alt'],'additionalProperties':False}
def block(kind,fields,required):return {'type':'object','properties':{'type':{'const':kind},**fields},'required':['type',*required],'additionalProperties':False}
BLOCKS_SCHEMA={'type':'array','maxItems':150,'items':{'oneOf':[
 block('ranked-list',{'title':SHORT,'intro':SHORT,'start':{'type':'integer','minimum':1,'maximum':1000},'items':{'type':'array','minItems':1,'maxItems':100,'items':{'type':'object','properties':{'title':SHORT,'author':SHORT,'note':TEXT},'required':['title','author','note'],'additionalProperties':False}}},['title','start','items']),
 block('sources',{'items':{'type':'array','maxItems':20,'items':{'type':'object','properties':{'title':SHORT,'url':SHORT},'required':['title','url'],'additionalProperties':False}}},['items']),block('paragraph',{'text':TEXT},['text']),block('heading',{'text':SHORT},['text']),
 block('image',{'src':SHORT,'alt':SHORT,'caption':SHORT},['src','alt']),
 block('quote',{'text':TEXT,'attribution':SHORT},['text']),
 block('qa',{'question':SHORT,'answer':TEXT},['question','answer']),
 block('checklist',{'title':SHORT,'items':{'type':'array','minItems':1,'maxItems':30,'items':SHORT}},['items']),
 block('step',{'title':SHORT,'text':TEXT},['title','text']),
 block('video',{'src':SHORT,'title':SHORT,'caption':SHORT,'description':TEXT},['src','title','description']),
 block('gallery',{'title':SHORT,'images':{'type':'array','minItems':2,'maxItems':12,'items':IMAGE}},['images']),
 block('callout',{'title':SHORT,'text':TEXT},['title','text']),
 block('thread',{'title':SHORT,'text':TEXT,'thread_id':{'type':'string','pattern':'^[A-Za-z0-9_-]{1,100}$'}},['title','text','thread_id'])]}}
HERO_LAYOUTS=['overlay-left','overlay-center','overlay-right','overlay-bottom','split']
FORMATS=['interview','checklist','photo-story','how-to','personal-story','video','gallery','conversation','profile','opinion','ranked-list']

def safe_media(url,video=False):
    if not isinstance(url,str):return False
    if not video and re.fullmatch(r'/media/[A-Za-z0-9_-]+\.webp',url):return True
    if not video and re.fullmatch(r'/assets/[A-Za-z0-9_-]+\.(?:jpg|webp|png)',url):return True
    try:parsed=urlsplit(url);port=parsed.port
    except ValueError:return False
    allowed={'mdn.github.io'} if video else {'images.unsplash.com'}
    return parsed.scheme=='https' and parsed.hostname in allowed and not parsed.username and port in {None,443} and (not video or parsed.path.startswith('/shared-assets/videos/') and parsed.path.endswith('.mp4'))

def validate_blocks(blocks):
    from jsonschema import Draft202012Validator
    errors=list(Draft202012Validator(BLOCKS_SCHEMA).iter_errors(blocks))
    if errors:raise ValueError('Invalid editorial block structure.')
    for item in blocks:
        if item['type']=='sources':
            for source in item['items']:
                try:url=urlsplit(source['url']);valid=url.scheme=='https' and bool(url.hostname) and not url.username
                except ValueError:valid=False
                if not valid:raise ValueError('Sources require HTTPS links.')
        if item['type'] in {'image','video'} and not safe_media(item['src'],item['type']=='video'):raise ValueError('Unapproved media URL.')
        if item['type']=='gallery':
            for image in item['images']:
                if not safe_media(image['src']):raise ValueError('Unapproved gallery image URL.')

def blocks_text(blocks):
    text=[]
    for b in blocks:
        for field in ['text','title','question','answer','description','caption','attribution']:
            if b.get(field):text.append(b[field])
        text.extend(item if isinstance(item,str) else ' '.join(item.get(key,'') for key in ['title','author','note']) for item in b.get('items',[]))
        text.extend(image.get('caption','') for image in b.get('images',[]))
    return '\n\n'.join(text)

def render_blocks(data):
    e=lambda value:html.escape(str(value),quote=True)
    blocks=data.get('blocks') or [{'type':'heading','text':s['heading']} if not s.get('body') else {'type':'legacy','heading':s['heading'],'body':s['body']} for s in data.get('sections',[])]
    output=[];toc=[];step=0;checks=0;gallery=0;list_started=False
    for index,b in enumerate(blocks):
        kind=b['type'];anchor='section-'+str(index)
        if kind in {'heading','step','checklist','gallery','ranked-list'}:
            title=b.get('text') if kind=='heading' else b.get('title')
            if title:toc.append((anchor,title))
        if kind=='ranked-list':
            if not list_started:
                total=sum(len(item['items']) for item in blocks if item['type']=='ranked-list');shelf_count=sum(item['type']=='ranked-list' for item in blocks)
                output.append('<details class="book-mobile-nav"><summary>Browse the '+str(shelf_count)+' shelves</summary><nav aria-label="Book shelves">'+''.join('<a href="#section-'+str(n)+'">'+e(shelf['title'])+'</a>' for n,shelf in enumerate(blocks) if shelf['type']=='ranked-list')+'</nav></details>')
                output.append('<div class="book-list-tools" role="search" aria-label="Find a book in this list"><label for="book-query">Find your next read</label><input id="book-query" type="search" placeholder="Search by title, author or idea…" autocomplete="off"><p id="book-list-status" role="status">'+str(total)+' books · '+str(shelf_count)+' shelves</p></div>')
                list_started=True
            entries=''.join('<li class="book-entry" id="book-'+str(b['start']+n)+'" value="'+str(b['start']+n)+'"><a class="book-rank" href="#book-'+str(b['start']+n)+'" aria-label="Book '+str(b['start']+n)+': '+e(item['title'])+'">'+str(b['start']+n).zfill(2)+'</a><div><h3>'+e(item['title'])+'</h3><p class="book-author">'+e(item['author'])+'</p><p class="book-note">'+e(item['note'])+'</p></div></li>' for n,item in enumerate(b['items']))
            output.append('<section class="book-shelf" id="'+anchor+'"><header><p class="book-range">'+str(b['start']).zfill(2)+' — '+str(b['start']+len(b['items'])-1)+'</p><h2>'+e(b['title'])+'</h2><p class="book-shelf-intro">'+e(b.get('intro',''))+'</p></header><ol start="'+str(b['start'])+'" role="list">'+entries+'</ol></section>')
        elif kind=='sources':output.append('<section class="article-sources"><h2>Sources</h2><ol>'+''.join('<li><a href="'+e(source['url'])+'" rel="noreferrer">'+e(source['title'])+'</a></li>' for source in b['items'])+'</ol></section>')
        elif kind=='legacy':output.append('<section><h2>'+e(b['heading'])+'</h2><p>'+e(b['body'])+'</p></section>')
        elif kind=='paragraph':output.append('<p>'+e(b['text'])+'</p>')
        elif kind=='heading':output.append('<h2 id="'+anchor+'">'+e(b['text'])+'</h2>')
        elif kind=='image':output.append('<figure class="inline-photo"><img loading="lazy" src="'+e(b['src'])+'" alt="'+e(b['alt'])+'"><figcaption>'+e(b.get('caption',''))+'</figcaption></figure>')
        elif kind=='quote':
            attribution=b.get('attribution','');author,separator,source=attribution.partition(' · ')
            caption=('<figcaption><span class="quote-author">'+e(author)+'</span>'+('<span class="quote-source">'+e(source)+'</span>' if separator else '')+'</figcaption>') if attribution else ''
            output.append('<figure class="editorial-quote"><blockquote><p>'+e(b['text'])+'</p></blockquote>'+caption+'</figure>')
        elif kind=='qa':output.append('<section class="qa"><h2>'+e(b['question'])+'</h2><p>'+e(b['answer'])+'</p></section>')
        elif kind=='checklist':
            checks+=1;items=''.join('<li><label><input type="checkbox"><span>'+e(item)+'</span></label></li>' for item in b['items'])
            output.append('<section class="article-checklist" id="'+anchor+'"><h2>'+e(b.get('title','Your checklist'))+'</h2><p class="form-hint">Check items as you go. Your selections stay in this page only.</p><ul>'+items+'</ul></section>')
        elif kind=='step':
            step+=1;output.append('<section class="article-step" id="'+anchor+'"><span class="step-number">'+str(step).zfill(2)+'</span><div><h2>'+e(b['title'])+'</h2><p>'+e(b['text'])+'</p></div></section>')
        elif kind=='video':output.append('<figure class="article-video"><video controls playsinline preload="metadata" aria-label="'+e(b['title'])+'"><source src="'+e(b['src'])+'" type="video/mp4">Your browser cannot play this video. <a href="'+e(b['src'])+'">Open video</a>.</video><figcaption>'+e(b.get('caption',''))+'</figcaption><details><summary>Video description</summary><p>'+e(b['description'])+'</p></details></figure>')
        elif kind=='gallery':
            gallery+=1;images=''.join('<figure><a class="gallery-image" data-gallery="gallery-'+str(gallery)+'" href="'+e(image['src'])+'" data-alt="'+e(image['alt'])+'" data-caption="'+e(image.get('caption',''))+'"><img loading="lazy" src="'+e(image['src'])+'" alt="'+e(image['alt'])+'"><span>View image '+str(n+1)+'</span></a><figcaption>'+e(image.get('caption',''))+'</figcaption></figure>' for n,image in enumerate(b['images']))
            output.append('<section id="'+anchor+'" class="article-gallery"><h2>'+e(b.get('title','In pictures'))+'</h2><p class="form-hint">Select a photograph to view the gallery.</p><div class="gallery-grid">'+images+'</div></section>')
        elif kind=='callout':output.append('<aside class="article-callout"><h3>'+e(b['title'])+'</h3><p>'+e(b['text'])+'</p></aside>')
        elif kind=='thread':output.append('<aside class="article-thread"><p class="eyebrow">CONTINUE THE CONVERSATION</p><h2>'+e(b['title'])+'</h2><p>'+e(b['text'])+'</p><a class="button" href="/conversations/'+e(b['thread_id'])+'">Open the conversation →</a></aside>')
    navigation='<aside class="article-toc"><p>ON THIS PAGE</p><nav aria-label="On this page">'+''.join('<a href="#'+id+'">'+e(title)+'</a>' for id,title in toc)+'</nav></aside>' if len(toc)>1 else ''
    return '<div class="article-layout">'+navigation+'<div class="article-prose">'+''.join(output)+'</div></div>'
