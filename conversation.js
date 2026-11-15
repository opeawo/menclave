(() => {
  const $ = id => document.getElementById(id);
  let reportPost = '';
  let session;
  async function send(path,data) {
    if (!session) session = fetch('/api/session').then(async response => {if(!response.ok)throw Error('Refresh this page and try again.');return response.json();});
    const {csrf} = await session;
    const response = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)});
    const result = await response.json();
    if(!response.ok)throw Error(result.error || 'Please try again.');
    return result;
  }
  document.querySelectorAll('[data-report]').forEach(button=>button.addEventListener('click',()=>{reportPost=button.dataset.report;$('report-status').textContent='';$('report-dialog').showModal();}));
  $('close-report').addEventListener('click',()=>$('report-dialog').close());
  $('report-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.currentTarget.querySelector('[type=submit]');button.disabled=true;try{const result=await send('/api/reports',{post:reportPost,reason:$('report-reason').value});$('report-status').textContent=result.message;}catch(error){$('report-status').textContent=error.message;}finally{button.disabled=false;}});
  $('reply-form')?.addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,button=form.querySelector('[type=submit]');button.disabled=true;$('reply-status').textContent='Sending…';try{const result=await send('/api/replies',{parent:form.dataset.thread,body:$('reply-body').value});$('reply-status').textContent=result.message;form.reset();}catch(error){$('reply-status').textContent=error.message;}finally{button.disabled=false;}});
})();
