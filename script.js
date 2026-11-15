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
(() => {
  const search = document.querySelector('#story-search');
  const category = document.querySelector('#category-filter');
  if (!search || !category) return;
  const cards = [...document.querySelectorAll('.archive-card')];
  const params = new URLSearchParams(location.search);
  search.value = params.get('q') || '';
  category.value = params.get('category') || '';
  const filter = () => {
    const query = search.value.trim().toLocaleLowerCase();
    let count = 0;
    cards.forEach(card => {
      card.hidden = !(card.textContent.toLocaleLowerCase().includes(query) && (!category.value || card.dataset.category === category.value));
      if (!card.hidden) count++;
    });
    document.querySelector('#archive-status').textContent = `${count} ${count === 1 ? 'story' : 'stories'}`;
    document.querySelector('#archive-empty').hidden = count !== 0;
    const url = new URL(location.href);
    for (const [key, value] of [['q', search.value], ['category', category.value]]) {
      if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
    }
    history.replaceState(null, '', url);
  };
  search.addEventListener('input', filter);
  category.addEventListener('change', filter);
  search.form.addEventListener('submit', event => event.preventDefault());
  search.form.addEventListener('reset', () => { search.value = ''; category.value = ''; filter(); });
  filter();
})();
