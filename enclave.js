(() => {
  const $ = id => document.getElementById(id);
  let csrf = '', reportPost = '', requestVersion = 0;
  const activeTopic = new URLSearchParams(location.search).get('topic') || '';
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
  function meta(post, label = (post.sample ? (post.staff ? (post.parent ? 'Sample moderator note' : 'Menclave · Sample conversation') : 'Sample conversation') : post.staff ? 'Menclave team' : 'Anonymous')) {
    const el = node('div',undefined,'thread-meta'); el.append(node('span',`${label} · ${date(post.created)}`),reportButton(post.id)); return el;
  }
  async function list() {
    const version = ++requestVersion;
    $('feed-status').textContent = 'Loading conversations…';
    const params = new URLSearchParams({q:'',topic:activeTopic});
    try {
      const {threads} = await api('/api/threads?'+params);
      if (version !== requestVersion) return;
      const url = new URL(location.href); url.searchParams.delete('q');
      if(activeTopic)url.searchParams.set('topic',activeTopic);else url.searchParams.delete('topic');
      history.replaceState(null,'',url);
      $('thread-list').replaceChildren();
      $('feed-status').textContent = `${threads.length}${threads.length === 100 ? '+' : ''} ${threads.length === 1 ? 'conversation' : 'conversations'} · Newest first`;
      if (!threads.length) {
        const empty = node('div',undefined,'empty-feed');
        empty.append(node('h3','There’s room for your voice.'),node('p','No conversations here yet. Be the first to share a question or perspective.'));
        const link = node('a','Start a conversation →','back-link'); link.href='#ask';empty.append(link);$('thread-list').append(empty);
      }
      threads.forEach(post => {
        const card = node('article',undefined,'thread-card');
        const button = node('a',post.title,'thread-open');button.href='/conversations/'+encodeURIComponent(post.id);
        card.append(meta(post),node('p',post.topic,'eyebrow'),button,node('p',post.body.slice(0,220)+(post.body.length>220?'…':''),'thread-excerpt'),node('p',`${post.replies} ${post.replies === 1?'reply':'replies'} · View conversation →`,'form-hint'));
        $('thread-list').append(card);
      });
    } catch(error) { if (version === requestVersion) $('feed-status').textContent = error.message; }
  }
  document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click',() => $(button.dataset.close).close()));
  async function submit(form, status, path, data, success) {
    const button=form.querySelector('[type=submit]');button.disabled=true;status.textContent='Sending…';
    try { const result=await api(path,data);status.textContent=result.message;success(); }
    catch(error) {status.textContent=error.message;}
    finally {button.disabled=false;}
  }
  $('ask-form')?.addEventListener('submit',event => {event.preventDefault();const form=event.currentTarget;submit(form,$('ask-status'),'/api/threads',Object.fromEntries(new FormData(form)),()=>{form.reset();$('ask').open=false;});});
  $('report-form').addEventListener('submit',event => {event.preventDefault();submit(event.currentTarget,$('report-status'),'/api/reports',{post:reportPost,reason:$('report-reason').value},()=>{});});
  const params = new URLSearchParams(location.search);
  fetch('/api/community-config').then(response=>response.json()).then(config=>{
    if(config.text && config.text !== 'Protect privacy. Be respectful. No hate, harassment or spam. Posts are reviewed.'){
      const list=document.querySelector('#guidelines ol');
      if(list){const item=document.createElement('li');item.textContent=config.text;list.replaceChildren(item);}
    }
  }).catch(()=>{});
  $('composer-cancel').addEventListener('click',()=>{$('ask').open=false;});
  $('ask').addEventListener('toggle',()=>{if($('ask').open)$('ask-title')?.focus();});
  document.addEventListener('click',event=>{if(event.target.closest('a[href="#ask"]'))$('ask').open=true;});
  if(location.hash==='#ask')$('ask').open=true;
  list();

})();
