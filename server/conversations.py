"""Permanent, server-rendered pages for approved anonymous conversations."""
from datetime import datetime,timezone
from urllib.parse import quote
from flask import render_template_string,request
from server.publishing import shell

def stamp(value):return datetime.fromtimestamp(value,timezone.utc).isoformat()
def label(post):return 'Sample moderator note' if post['sample'] and post['staff'] else 'Sample conversation' if post['sample'] else 'Menclave team' if post['staff'] else 'Anonymous'
def url(id):return '/conversations/'+quote(id,safe='')

CARD='''{% for post in posts %}<article class="thread-card"><div class="thread-meta"><span>{{label(post)}} · <time datetime="{{stamp(post.created)}}">{{stamp(post.created)[:10]}}</time></span></div><p class="eyebrow">{{post.topic}}</p><a class="thread-open" href="{{url(post.id)}}">{{post.title}}</a><p class="thread-excerpt">{{post.body[:220]}}{% if post.body|length>220 %}…{% endif %}</p><p class="form-hint">{{post.replies}} {{'reply' if post.replies==1 else 'replies'}} · View conversation →</p></article>{% else %}<div class="empty-feed"><h3>There’s room for your voice.</h3><p>Share a question or perspective.</p><a href="#ask">Start a conversation →</a></div>{% endfor %}'''

def listing(platform):
    from server.app import ROOT
    posts=platform.store.listing(topic=request.args.get('topic',''))
    source=(ROOT/'enclave.html').read_text()
    cards=render_template_string(CARD,posts=posts,label=label,stamp=stamp,url=url)
    source=source.replace('<div id="thread-list"></div>','<div id="thread-list">'+cards+'</div>').replace('Loading conversations…',str(len(posts))+' conversations · Newest first')
    source=source.replace('</head>','<link rel="canonical" href="'+__import__('html').escape(request.host_url.rstrip('/')+'/conversations',quote=True)+'"></head>')
    return source

def detail(platform,id):
    post=platform.store.thread(id)
    if not post:return '',404
    base=(__import__('os').environ.get('ENCLAVE_ORIGIN') or request.host_url.rstrip('/'));canonical=base+url(id)
    structured={'@context':'https://schema.org','@type':'DiscussionForumPosting','headline':post['title'],'text':post['body'],'datePublished':stamp(post['created']),'url':canonical,'mainEntityOfPage':canonical,'author':{'@type':'Person','name':label(post)},'commentCount':len(post['replies']),'comment':[{'@type':'Comment','text':r['body'],'datePublished':stamp(r['created']),'url':canonical+'#reply-'+r['id'],'author':{'@type':'Person','name':label(r)}} for r in post['replies']]}
    return shell(platform,post['title'],post['body'][:160],'''<div class="conversation-page"><a class="back-link" href="/conversations">← Conversations</a><article class="conversation-post"><p class="eyebrow">{{post.topic}}</p><h1>{{post.title}}</h1><div class="thread-meta"><span>{{label(post)}} · <time datetime="{{stamp(post.created)}}">{{stamp(post.created)[:10]}}</time></span><button class="report-button" data-report="{{post.id}}" type="button">Report</button></div><div class="post-body">{{post.body}}</div></article><section class="conversation-replies" aria-labelledby="replies-heading"><h2 id="replies-heading">{{post.replies|length}} {{'reply' if post.replies|length==1 else 'replies'}}</h2>{% for reply in post.replies %}<article class="reply-card" id="reply-{{reply.id}}"><div class="thread-meta"><span>{{label(reply)}} · <time datetime="{{stamp(reply.created)}}">{{stamp(reply.created)[:10]}}</time></span><button type="button" class="report-button" data-report="{{reply.id}}">Report</button></div><div class="post-body">{{reply.body}}</div></article>{% endfor %}</section>{% if post.locked %}<p class="form-hint">This conversation is closed to new replies.</p>{% else %}<section id="reply-section"><h2>Add your perspective.</h2><form id="reply-form" data-thread="{{post.id}}"><label for="reply-body">Your reply</label><textarea id="reply-body" name="body" minlength="20" maxlength="5000" rows="5" required></textarea><p class="form-hint">Be kind. Leave out identifying details. Replies are reviewed before publication.</p><button type="submit" class="button">Submit reply →</button><p id="reply-status" role="status"></p></form></section>{% endif %}</div><dialog id="report-dialog" class="community-dialog" aria-labelledby="report-title"><button class="dialog-close" type="button" id="close-report">Close ×</button><h2 id="report-title">Flag for review.</h2><form id="report-form"><label for="report-reason">What concerns you?</label><select id="report-reason" required><option>Identifying information</option><option>Harassment or hate</option><option>Spam or promotion</option><option>Harmful content</option><option>Other concern</option></select><button type="submit" class="button">Send report →</button><p id="report-status" role="status"></p></form></dialog>{% if not post.sample %}<script type="application/ld+json">{{structured|tojson}}</script>{% endif %}<script defer src="/conversation.js"></script>''',post=post,label=label,stamp=stamp,structured=structured,story={'concept':post['sample'],'canonical':url(id)}),200
