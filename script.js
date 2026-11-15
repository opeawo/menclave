(() => {
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#mobile-nav');
  if (toggle && nav) {
    const close = () => { nav.hidden = true; toggle.setAttribute('aria-expanded', 'false'); toggle.setAttribute('aria-label', 'Open navigation'); };
    toggle.addEventListener('click', () => { const expanded = toggle.getAttribute('aria-expanded') === 'true'; nav.hidden = expanded; toggle.setAttribute('aria-expanded', String(!expanded)); toggle.setAttribute('aria-label', expanded ? 'Open navigation' : 'Close navigation'); });
    nav.querySelectorAll('a').forEach(link => link.addEventListener('click', close));
    document.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
  }
  const form = document.querySelector('#newsletter-form');
  if (form) {
    form.addEventListener('submit', event => {
      event.preventDefault();
      const status = document.querySelector('#form-message');
      const button = form.querySelector('button');
      button.disabled = true;
      (async () => {
        try {
          const session = await fetch('/api/session');
          if (!session.ok) throw Error('Newsletter subscriptions are not active. No email has been stored.');
          const {csrf} = await session.json();
          const response = await fetch('/api/newsletter/subscribe', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({email:form.elements.email.value})});
          const result = await response.json();
          status.textContent = result.message || result.error || 'Please try again.';
          if (response.ok) form.reset();
        } catch (error) { status.textContent = 'We could not confirm your subscription request. Please try again later.'; }
        finally {button.disabled=false;}
      })();
    });
  }
})();
(() => {
  const input = document.querySelector('#global-query');
  if (!input) return;
  input.value = new URLSearchParams(location.search).get('q') || '';
  document.addEventListener('keydown', event => {
    const editing = event.target.closest('input, textarea, select, [contenteditable="true"]');
    if (event.key === '/' && !editing && !event.ctrlKey && !event.metaKey && !document.querySelector('dialog[open]')) {
      event.preventDefault(); input.focus();
    }
    if (event.key === 'Escape' && document.activeElement === input) input.blur();
  });
})();
