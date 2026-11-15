(() => {
  const $ = id => document.getElementById(id);
  let csrf = '', activeThread = '', reportPost = '', requestVersion = 0;
  const session = fetch('/api/session').then(async r => { if (!r.ok) throw Error('Community server unavailable.'); csrf = (await r.json()).csrf; });
  session.catch(() => {});
  const node = (tag, text, className) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; };
  async function api(path, data) {
    if (data) await session;
    const response = await fetch(path, data ? {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)} : {});
    const payload = await response.json().catch(() => ({error:'Community server unavailable. Start the community server to use this page.'}));
    if (!response.ok) throw Error(payload.error || 'Something went wrong. Please try again.');
    return payload;
  }
  const date = seconds => new Date(seconds * 1000).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'});
  function reportButton(id) {
    const button = node('button','Report','report-button'); button.type = 'button';
    button.addEventListener('click', () => { reportPost = id; $('report-status').textContent = ''; $('report-dialog').showModal(); });
    return button;
  }
  function meta(post, label = 'Anonymous') {
    const el = node('div',undefined,'thread-meta'); el.append(node('span',`${label} · ${date(post.created)}`),reportButton(post.id)); return el;
  }
  async function list() {
    const version = ++requestVersion;
    $('feed-status').textContent = 'Loading conversations…';
    const params = new URLSearchParams({q:$('conversation-search').value,topic:$('topic-filter').value});
    try {
      const {threads} = await api('/api/threads?'+params);
      if (version !== requestVersion) return;
      const url = new URL(location.href); url.search = params.toString(); history.replaceState(null,'',url);
      $('thread-list').replaceChildren();
      $('feed-status').textContent = `${threads.length}${threads.length === 100 ? '+' : ''} ${threads.length === 1 ? 'conversation' : 'conversations'} · Newest first`;
      if (!threads.length) {
        const empty = node('div',undefined,'empty-feed');
        empty.append(node('h3','There’s room for your voice.'),node('p','No conversations here yet. Try another topic or start a conversation below.'));
        const link = node('a','Start a conversation →','back-link'); link.href='#ask';empty.append(link);$('thread-list').append(empty);
      }
      threads.forEach(post => {
        const card = node('article',undefined,'thread-card');
        const button = node('button',post.title,'thread-open');button.type='button';button.addEventListener('click',()=>openThread(post.id));
        card.append(node('p',post.topic,'eyebrow'),button,node('p',post.body.slice(0,220)+(post.body.length>220?'…':''),'thread-excerpt'),node('p',`${post.replies} ${post.replies === 1?'reply':'replies'}`,'form-hint'),meta(post));
        $('thread-list').append(card);
      });
    } catch(error) { if (version === requestVersion) $('feed-status').textContent = error.message; }
  }
  async function openThread(id) {
    activeThread = id; $('thread-content').replaceChildren(node('h2','Loading conversation…')); $('reply-section').hidden=true;
    if (!$('thread-dialog').open) $('thread-dialog').showModal();
    $('reply-form').reset();$('reply-status').textContent='';
    try {
      const post = await api('/api/threads/'+encodeURIComponent(id));
      if (activeThread !== id) return;
      const heading = node('h2',post.title);heading.id='thread-title';
      $('thread-content').replaceChildren(node('p',post.topic,'eyebrow'),heading,meta(post),node('p',post.body,'post-body'),node('h3',`${post.replies.length} replies`));
      post.replies.forEach(reply => {const el=node('article',undefined,'reply-card');el.append(meta(reply),node('p',reply.body,'post-body'));$('thread-content').append(el);});
      $('reply-section').hidden=false;
    } catch(error) { const heading=node('h2',error.message);heading.id='thread-title';$('thread-content').replaceChildren(heading); }
  }
  document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click',() => $(button.dataset.close).close()));
  async function submit(form, status, path, data, success) {
    const button=form.querySelector('[type=submit]');button.disabled=true;status.textContent='Sending…';
    try { const result=await api(path,data);status.textContent=result.message;success(); }
    catch(error) {status.textContent=error.message;}
    finally {button.disabled=false;}
  }
  $('ask-form').addEventListener('submit',event => {event.preventDefault();const form=event.currentTarget;submit(form,$('ask-status'),'/api/threads',Object.fromEntries(new FormData(form)),()=>form.reset());});
  $('reply-form').addEventListener('submit',event => {event.preventDefault();const form=event.currentTarget;submit(form,$('reply-status'),'/api/replies',{parent:activeThread,body:$('reply-body').value},()=>form.reset());});
  $('report-form').addEventListener('submit',event => {event.preventDefault();submit(event.currentTarget,$('report-status'),'/api/reports',{post:reportPost,reason:$('report-reason').value},()=>{});});
  $('community-search').addEventListener('submit',event=>{event.preventDefault();list();});
  $('topic-filter').addEventListener('change',list);
  const params = new URLSearchParams(location.search);$('conversation-search').value=params.get('q') || '';$('topic-filter').value=params.get('topic') || '';
  list();
})();
