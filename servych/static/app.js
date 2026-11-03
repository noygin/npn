// Копирование ссылок
document.querySelectorAll("[data-copy]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const text = btn.dataset.copy;
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    const old = btn.textContent;
    btn.textContent = "Скопировано ✓";
    setTimeout(() => { btn.textContent = old; }, 2000);
  });
});

// Вкладки устройств: сразу открываем ту, с которой зашли
const tabs = document.querySelectorAll("[data-tab]");
function selectTab(key) {
  tabs.forEach((t) => t.setAttribute("aria-selected", String(t.dataset.tab === key)));
  document.querySelectorAll("[data-panel]").forEach((p) => { p.hidden = p.dataset.panel !== key; });
}
if (tabs.length) {
  tabs.forEach((t) => t.addEventListener("click", () => selectTab(t.dataset.tab)));
  const ua = navigator.userAgent;
  const isIpad = navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
  if (/iPhone|iPad|iPod/.test(ua) || isIpad) selectTab("iphone");
  else if (/Android/.test(ua)) selectTab("android");
  else selectTab("computer");
}
