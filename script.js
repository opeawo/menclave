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
      if (status) status.textContent = 'Newsletter subscriptions are not active in this design preview. No email has been stored.';
    });
  }
})();