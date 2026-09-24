if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

for (const el of document.querySelectorAll("[data-countdown]")) {
  const end = Date.parse(el.dataset.countdown);
  const tick = () => {
    const ms = end - Date.now();
    if (ms <= 0) {
      el.textContent = "expired";
      return;
    }
    const m = Math.floor(ms / 60000);
    const s = Math.floor((ms % 60000) / 1000);
    el.textContent = `${m}:${String(s).padStart(2, "0")} left`;
    requestAnimationFrame(() => setTimeout(tick, 250));
  };
  tick();
}
