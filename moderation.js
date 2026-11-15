(() => {
  const $ = id => document.getElementById(id);
  let key = '', csrf = '';
  const node=(tag,text)=>{const el=document.createElement(tag);el.textContent=text;return el;};
  async function api(data) {
    const response=await fetch('/api/moderation', {method:data?'POST':'GET',headers:{'Authorization':'Bearer '+key,...(data?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{})},...(data?{body:JSON.stringify(data)}:{})});
    const result=await response.json();if(!response.ok)throw Error(result.error || 'Unable to load moderation.');return result;
  }
  async function action(id,action) {
    if(action==='remove' && !confirm('Permanently remove this text and any replies?'))return;
    try {await api({id,action});await load();$('moderator-status').textContent='Moderation saved.';}catch(error){$('moderator-status').textContent=error.message;}
  }
  function button(id,label,value) {const el=node('button',label);el.type='button';el.addEventListener('click',()=>action(id,value));return el;}
  async function load() {
    const result=await api();$('pending-list').replaceChildren();$('reports-list').replaceChildren();
    result.pending.forEach(post=>{const card=node('article','');card.className='moderation-item';card.append(node('p',`${post.topic} · ${post.parent?'Reply to '+post.parent:'Question'}`),node('h3',post.title),node('p',post.body),button(post.id,'Approve','approve'),button(post.id,'Remove','remove'));$('pending-list').append(card);});
    result.reports.forEach(report=>{const card=node('article','');card.className='moderation-item';card.append(node('h3',report.reason),node('h4',report.title),node('p',report.body),button(report.post,'Remove post','remove'),button(report.id,'Dismiss report','dismiss'));$('reports-list').append(card);});
    if(!result.pending.length)$('pending-list').append(node('p','No posts awaiting review.'));
    if(!result.reports.length)$('reports-list').append(node('p','No unresolved reports.'));
    $('moderator-tools').hidden=false;
  }
  const lock=()=>{key='';csrf='';$('moderator-key').value='';$('pending-list').replaceChildren();$('reports-list').replaceChildren();$('moderator-tools').hidden=true;$('moderator-status').textContent='Queue locked.';};
  $('moderator-login').addEventListener('submit',async event=>{event.preventDefault();key=$('moderator-key').value;$('moderator-key').value='';try{const response=await fetch('/api/session');csrf=(await response.json()).csrf;await load();$('moderator-status').textContent='Queue unlocked. The key stays in this tab’s memory only.';}catch(error){lock();$('moderator-status').textContent=error.message;}});
  $('lock-queue').addEventListener('click',lock);
  $('refresh-queue').addEventListener('click',()=>load().catch(error=>{$('moderator-status').textContent=error.message;}));
  window.addEventListener('pagehide',lock);
})();
