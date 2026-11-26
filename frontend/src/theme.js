/* Runs before styles load, so the chosen theme never flashes the wrong palette. */
(function () {
  const key = 'fable_theme';
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const listeners = new Set();
  let choice = 'system';
  try { choice = localStorage.getItem(key) || 'system'; } catch (_) {}
  if (!['light', 'dark', 'system'].includes(choice)) choice = 'system';
  function apply() {
    document.documentElement.dataset.theme = choice === 'system' ? (media.matches ? 'dark' : 'light') : choice;
    listeners.forEach(listener => listener(choice));
  }
  window.RPTheme = {
    getChoice: () => choice,
    setChoice(value) {
      if (!['light', 'dark', 'system'].includes(value)) return;
      choice = value;
      try { localStorage.setItem(key, value); } catch (_) {}
      apply();
    },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); }
  };
  media.addEventListener('change', apply);
  window.addEventListener('storage', event => {
    if (event.key === key) {
      choice = ['light', 'dark', 'system'].includes(event.newValue) ? event.newValue : 'system';
      apply();
    }
  });
  apply();
})();
