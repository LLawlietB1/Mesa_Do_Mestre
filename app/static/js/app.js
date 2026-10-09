/* Mesa do Mestre — interações locais. Sem frameworks; alterações persistentes vão ao servidor. */
(function () {
  "use strict";

  const csrf = () => (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  /* ---- Menu lateral (mobile) ---- */
  const sidebar = document.getElementById("sidebar");
  const backdrop = document.querySelector(".sidebar-backdrop");
  const toggle = document.querySelector("[data-nav-toggle]");
  function setNav(open) {
    if (!sidebar || !toggle) return;
    sidebar.classList.toggle("is-open", open);
    backdrop.classList.toggle("is-open", open);
    backdrop.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
  }
  if (toggle) toggle.addEventListener("click", () => setNav(!sidebar.classList.contains("is-open")));
  if (backdrop) backdrop.addEventListener("click", () => setNav(false));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") setNav(false); });

  /* ---- Toasts ---- */
  document.querySelectorAll(".toast").forEach((t) => {
    const close = () => { t.classList.add("is-leaving"); setTimeout(() => t.remove(), 300); };
    t.querySelector("[data-toast-close]").addEventListener("click", close);
    if (!t.classList.contains("toast--error")) setTimeout(close, 9000);
  });

  /* ---- Selects que enviam o formulário ao mudar ---- */
  document.querySelectorAll("select[data-autosubmit]").forEach((s) => {
    s.addEventListener("change", () => s.form && s.form.submit());
  });

  /* ---- Confirmação antes de operações destrutivas ---- */
  const dialog = document.getElementById("confirm-dialog");
  const confirmText = document.getElementById("confirm-text");
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (!(form instanceof HTMLFormElement) || !form.dataset.confirm || form.dataset.confirmed === "1") return;
    e.preventDefault();
    if (!dialog || typeof dialog.showModal !== "function") {
      if (window.confirm(form.dataset.confirm)) { form.dataset.confirmed = "1"; form.submit(); }
      return;
    }
    confirmText.textContent = form.dataset.confirm;
    dialog.returnValue = "cancel";
    dialog.showModal();
    dialog.addEventListener("close", function onClose() {
      dialog.removeEventListener("close", onClose);
      if (dialog.returnValue === "ok") { form.dataset.confirmed = "1"; form.requestSubmit ? form.requestSubmit(e.submitter || undefined) : form.submit(); }
    });
  }, true);

  /* ---- Estado de carregamento nos formulários ---- */
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (e.defaultPrevented || !form.matches || !form.matches("[data-loading-form]")) return;
    const btn = form.querySelector('button[type="submit"]');
    if (btn) {
      btn.classList.add("is-loading");
      if (btn.dataset.loadingText) btn.textContent = btn.dataset.loadingText;
      setTimeout(() => { btn.disabled = true; }, 0); // não bloqueia o envio
    }
  });

  /* ---- Efeitos visuais ---- */
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Número que "rola" até o valor final.
  function tween(el, to, ms) {
    const from = Number(el.textContent) || 0;
    if (reduced || from === to) { el.textContent = to; return; }
    const t0 = performance.now();
    const step = (t) => {
      const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
      el.textContent = Math.round(from + (to - from) * e);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  document.querySelectorAll(".stat__n").forEach((n) => { const v = Number(n.textContent); if (!isNaN(v)) { n.textContent = 0; tween(n, v, 900); } });
  document.querySelectorAll(".xp-list > .card").forEach((c, i) => c.style.setProperty("--i", Math.min(i, 12)));

  // Brilho que acompanha o cursor nos cartões.
  document.addEventListener("pointermove", (e) => {
    const card = e.target.closest && e.target.closest(".card");
    if (!card) return;
    const r = card.getBoundingClientRect();
    card.style.setProperty("--mx", (e.clientX - r.left) + "px");
    card.style.setProperty("--my", (e.clientY - r.top) + "px");
  }, { passive: true });

  // Explosão de faíscas douradas ao completar 100%.
  function sparkle(root) {
    if (reduced) return;
    const bar = root.querySelector("[data-xp-bar]");
    const box = bar.getBoundingClientRect(), host = root.getBoundingClientRect();
    for (let i = 0; i < 22; i++) {
      const s = document.createElement("span");
      s.className = "spark";
      s.style.left = (box.right - host.left - 6) + "px";
      s.style.top = (box.top - host.top + box.height / 2 - 3) + "px";
      const a = Math.random() * Math.PI * 2, d = 30 + Math.random() * 60;
      s.style.setProperty("--dx", Math.cos(a) * d + "px");
      s.style.setProperty("--dy", Math.sin(a) * d - 20 + "px");
      root.appendChild(s);
      setTimeout(() => s.remove(), 1000);
    }
  }

  /* ---- Barra de XP (individual) ---- */
  function updateBar(root, percent) {
    const was = Number((root.querySelector("[data-xp-value]") || {}).textContent);
    root.querySelectorAll("[data-xp-bar]").forEach((bar) => {
      bar.setAttribute("aria-valuenow", percent);
      bar.classList.toggle("progress--full", percent === 100);
      bar.querySelector(".progress__fill").style.width = percent + "%";
    });
    root.querySelectorAll("[data-xp-value]").forEach((n) => tween(n, percent, 700));
    const full = root.querySelector("[data-xp-full]");
    if (full) full.hidden = percent !== 100;
    if (percent !== was) {
      root.classList.remove("is-bump"); void root.offsetWidth; root.classList.add("is-bump");
      if (percent === 100) sparkle(root);
    }
  }

  async function sendXP(root, payload) {
    const status = root.querySelector("[data-xp-status]");
    root.classList.add("is-busy");
    status.className = "xp__status"; status.textContent = "Salvando…";
    try {
      const res = await fetch(root.dataset.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({ ok: false, error: "Resposta inválida do servidor." }));
      if (!data.ok) {
        status.className = "xp__status is-error";
        status.textContent = data.error || "Não foi possível salvar.";
        if (typeof data.percent === "number") updateBar(root, data.percent);
        return;
      }
      updateBar(root, data.percent);          // valor persistido pelo servidor
      const cycle = root.querySelector("[data-xp-cycle]");
      if (cycle) cycle.textContent = data.cycle;
      status.className = "xp__status is-ok";
      status.textContent = data.changed ? data.message : "Sem alteração.";
    } catch (err) {
      status.className = "xp__status is-error";
      status.textContent = "Falha de conexão. Nada foi alterado.";
    } finally {
      root.classList.remove("is-busy");
    }
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-xp-action]");
    if (!btn) return;
    const root = btn.closest("[data-xp]");
    if (!root) return;
    const input = root.querySelector("[data-xp-input]");
    const action = btn.dataset.xpAction;
    const status = root.querySelector("[data-xp-status]");
    const needValue = () => {
      const v = input.value.trim();
      if (v === "" || !/^\d+$/.test(v) || Number(v) > 100) {
        status.className = "xp__status is-error";
        status.textContent = "Informe um número inteiro de 0 a 100.";
        input.focus();
        return null;
      }
      return Number(v);
    };
    if (action === "add") sendXP(root, { action: "add", value: Number(btn.dataset.xpValue) });
    else if (action === "add-input") { const v = needValue(); if (v !== null) sendXP(root, { action: "add", value: v * Number(btn.dataset.sign) }); }
    else if (action === "set-input") { const v = needValue(); if (v !== null) sendXP(root, { action: "set", value: v }); }
    else if (action === "reset") sendXP(root, { action: "reset" });
    else if (action === "complete") sendXP(root, { action: "complete" });
    else if (action === "new_cycle") sendXP(root, { action: "new_cycle" });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.matches && e.target.matches("[data-xp-input]")) {
      e.preventDefault();
      const root = e.target.closest("[data-xp]");
      const setBtn = root.querySelector('[data-xp-action="set-input"]');
      if (setBtn) setBtn.click();
    }
  });

  /* ---- Mensagens aos jogadores ---- */
  document.querySelectorAll("[data-msg]").forEach((card) => {
    const ta = card.querySelector("[data-msg-text]");
    const phone = card.dataset.phone;
    const status = card.querySelector("[data-msg-status]");
    const refresh = () => {
      const t = encodeURIComponent(ta.value);
      card.querySelector("[data-msg-wa]").href = "https://wa.me/" + phone.replace("+", "") + "?text=" + t;
      card.querySelector("[data-msg-sms]").href = "sms:" + phone + "?body=" + t;
      card.querySelector("[data-msg-count]").textContent = ta.value.length;
    };
    ta.addEventListener("input", refresh);
    const say = (msg, kind) => { status.className = "xp__status " + (kind || ""); status.textContent = msg; };
    const copy = card.querySelector("[data-msg-copy]");
    if (copy) copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(ta.value); say("Texto copiado.", "is-ok"); }
      catch (e) { ta.select(); say("Selecione e copie manualmente (Ctrl+C).", "is-error"); }
    });
    card.querySelectorAll("[data-msg-send]").forEach((btn) => btn.addEventListener("click", async () => {
      if (!ta.value.trim()) { say("Escreva a mensagem.", "is-error"); return; }
      btn.disabled = true; say("Enviando…");
      try {
        const res = await fetch(card.closest("[data-msg-root]").dataset.sendUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRFToken": csrf() },
          body: JSON.stringify({ player_id: Number(card.dataset.playerId), channel: btn.dataset.msgSend, body: ta.value }),
        });
        const data = await res.json().catch(() => ({ ok: false, error: "Resposta inválida do servidor." }));
        say(data.ok ? data.message : data.error, data.ok ? "is-ok" : "is-error");
      } catch (e) { say("Falha de conexão. Nada foi enviado.", "is-error"); }
      finally { btn.disabled = false; }
    }));
  });

  /* ---- Seleção para alteração coletiva ---- */
  const bulk = document.querySelector("[data-bulk-form]");
  if (bulk) {
    const items = () => Array.from(document.querySelectorAll("[data-bulk-item]"));
    const counter = bulk.querySelector("[data-bulk-count]");
    const refresh = () => { counter.textContent = items().filter((i) => i.checked).length; };
    document.addEventListener("change", (e) => { if (e.target.matches("[data-bulk-item]")) refresh(); });
    bulk.querySelector("[data-bulk-all]").addEventListener("click", () => { items().forEach((i) => (i.checked = true)); refresh(); });
    bulk.querySelector("[data-bulk-none]").addEventListener("click", () => { items().forEach((i) => (i.checked = false)); refresh(); });
    // Mostra claramente quem será afetado antes de enviar.
    // O texto de confirmação é montado no clique, antes do envio, para o diálogo listar os afetados.
    bulk.querySelectorAll("[data-bulk-submit]").forEach((b) => b.addEventListener("click", (e) => {
      const chosen = items().filter((i) => i.checked);
      const amount = bulk.querySelector("#bulk-amount");
      if (!chosen.length) { e.preventDefault(); counter.textContent = "0"; alert("Selecione ao menos um personagem."); return; }
      if (!amount.value) return; // deixa a validação nativa do navegador atuar
      const dir = b.value === "down" ? "reduzir" : "aumentar";
      bulk.dataset.confirm = `Vai ${dir} ${amount.value}% de XP de: ${chosen.map((i) => i.dataset.name).join(", ")}. Confirmar?`;
      bulk.dataset.confirmed = "";
    }));
  }
})();
