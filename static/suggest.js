/* Qidiruv takliflari (autocomplete). Matn faqat textContent orqali qo'yiladi (XSS xavfsiz). */
(function () {
  var input = document.getElementById("q");
  var box = document.getElementById("suggest");
  if (!input || !box) return;

  var endpoint = input.getAttribute("data-suggest-url");
  var timer = null, controller = null, items = [], active = -1;

  function esc(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

  function highlight(el, text, tokens) {
    if (!tokens.length) { el.textContent = text; return; }
    var re = new RegExp("(" + tokens.map(esc).join("|") + ")", "ig");
    text.split(re).forEach(function (part, i) {
      if (!part) return;
      if (i % 2 === 1) { var b = document.createElement("b"); b.textContent = part; el.appendChild(b); }
      else el.appendChild(document.createTextNode(part));
    });
  }

  function close() {
    box.hidden = true; box.textContent = ""; items = []; active = -1;
    input.setAttribute("aria-expanded", "false");
  }

  function heading(text) {
    var h = document.createElement("div"); h.className = "sg-head"; h.textContent = text; return h;
  }

  function render(data, q) {
    box.textContent = ""; items = []; active = -1;
    var tokens = q.split(/\s+/).filter(Boolean);
    if (!data.queries.length && !data.products.length) {
      var none = document.createElement("div");
      none.className = "sg-none"; none.textContent = "Hech narsa topilmadi";
      box.appendChild(none);
    }
    if (data.queries.length) {
      box.appendChild(heading("Qidiruv takliflari"));
      data.queries.forEach(function (s) {
        var a = document.createElement("a"); a.href = s.url; a.className = "sg-item"; a.setAttribute("role", "option");
        highlight(a, s.text, tokens); box.appendChild(a); items.push(a);
      });
    }
    if (data.products.length) {
      box.appendChild(heading("Smartfonlar"));
      data.products.forEach(function (p) {
        var a = document.createElement("a"); a.href = p.url; a.className = "sg-item sg-prod"; a.setAttribute("role", "option");
        var t = document.createElement("span"); t.className = "sg-title"; highlight(t, p.title, tokens);
        var pr = document.createElement("span"); pr.className = "sg-price";
        pr.textContent = "dan " + p.price;
        a.appendChild(t); a.appendChild(pr); box.appendChild(a); items.push(a);
      });
    }
    box.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function fetchSuggest() {
    var q = input.value.trim();
    if (q.length < 2) { close(); return; }
    if (controller) controller.abort();
    controller = new AbortController();
    fetch(endpoint + "?q=" + encodeURIComponent(q), { signal: controller.signal })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && input.value.trim() === q) render(d, q); })
      .catch(function () { /* so'rov bekor qilingan yoki tarmoq xatosi: jim */ });
  }

  function setActive(i) {
    if (!items.length) return;
    if (active >= 0) items[active].classList.remove("on");
    active = (i + items.length) % items.length;
    items[active].classList.add("on");
    items[active].scrollIntoView({ block: "nearest" });
  }

  input.addEventListener("input", function () {
    clearTimeout(timer); timer = setTimeout(fetchSuggest, 120);
  });
  input.addEventListener("focus", function () { if (input.value.trim().length >= 2) fetchSuggest(); });
  input.addEventListener("keydown", function (e) {
    if (box.hidden) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(active + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(active - 1); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); items[active].click(); }
    else if (e.key === "Escape") { close(); }
  });
  document.addEventListener("click", function (e) {
    if (!box.contains(e.target) && e.target !== input) close();
  });
})();
