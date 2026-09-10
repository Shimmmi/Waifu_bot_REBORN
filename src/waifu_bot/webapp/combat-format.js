/** Shared compact combat numbers for dungeons + overlay (overlay does not load app.js). */
(function (root) {
  function formatCombatNumber(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "0";
    const sign = n < 0 ? "-" : "";
    const abs = Math.abs(n);
    if (abs < 1000) return sign + String(Math.round(abs));
    if (abs < 1e6) {
      return sign + String(Math.round(abs)).replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f");
    }
    if (abs < 1e9) return sign + (abs / 1e6).toFixed(1) + "M";
    return sign + (abs / 1e9).toFixed(2) + "B";
  }

  function setCombatNumber(el, value, prefix) {
    if (!el) return;
    const raw = Number(value);
    const full = Number.isFinite(raw) ? String(Math.round(raw)) : "0";
    const shown = (prefix || "") + formatCombatNumber(value);
    el.textContent = shown;
    el.setAttribute("title", (prefix || "") + full);
    el.setAttribute("aria-label", (prefix || "") + full);
  }

  root.formatCombatNumber = formatCombatNumber;
  root.setCombatNumber = setCombatNumber;
  root.WaifuCombatFormat = { formatCombatNumber, setCombatNumber };
})(typeof window !== "undefined" ? window : globalThis);
