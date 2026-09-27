(() => {
  "use strict";
  fetch("/api/auth/session", { headers: { "Accept": "application/json" } })
    .then((response) => response.ok ? response.json() : { authenticated: false })
    .then((session) => {
      if (!session.authenticated) {
        const next = `${window.location.pathname}${window.location.search}`;
        window.location.replace(`/?next=${encodeURIComponent(next)}`);
      }
    })
    .catch(() => {
      const next = `${window.location.pathname}${window.location.search}`;
      window.location.replace(`/?next=${encodeURIComponent(next)}`);
    });
})();
