/* Publications: filter cards by publication year. */
(function () {
  "use strict";

  var bar = document.querySelector(".publication-filter");
  if (!bar) return;

  var buttons = Array.prototype.slice.call(bar.querySelectorAll(".publication-filter__btn"));
  var cards = Array.prototype.slice.call(document.querySelectorAll(".publication-card[data-year]"));
  var columns = Array.prototype.slice.call(document.querySelectorAll(".publication-column"));

  // Remember each column's count suffix ("work", "articles", "项成果", "篇论文")
  // so the visible count can be recomputed on every filter change.
  columns.forEach(function (column) {
    var count = column.querySelector(".publication-section-heading small");
    if (count) count.setAttribute("data-suffix", count.textContent.replace(/^\d+\s*/, ""));
  });

  function applyFilter(year) {
    cards.forEach(function (card) {
      card.hidden = year !== "all" && card.getAttribute("data-year") !== year;
    });
    columns.forEach(function (column) {
      var visible = column.querySelectorAll(".publication-card:not([hidden])").length;
      column.hidden = visible === 0;
      var count = column.querySelector(".publication-section-heading small");
      if (count) {
        var suffix = count.getAttribute("data-suffix") || "";
        count.textContent = visible + (suffix ? " " + suffix : "");
      }
    });
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      buttons.forEach(function (other) {
        var active = other === button;
        other.classList.toggle("is-active", active);
        other.setAttribute("aria-pressed", active ? "true" : "false");
      });
      applyFilter(button.getAttribute("data-year"));
    });
  });
})();

/* Publications: password-protected export of the full publication summary.
   The summary is rebuilt from the publication cards on every open, so it
   always reflects the latest content of this page. */
(function () {
  "use strict";

  var trigger = document.querySelector(".publication-export-btn");
  if (!trigger) return;

  var PASSWORD = "999926";

  var isZh = (document.documentElement.lang || "en").toLowerCase().indexOf("zh") === 0;
  var t = isZh
    ? {
        title: "导出发表信息",
        hint: "请输入密码以查看并导出发表信息汇总。",
        password: "密码",
        unlock: "解锁",
        cancel: "取消",
        wrong: "密码错误，请重试。",
        summaryTitle: "发表信息汇总",
        generatedPrefix: "生成于",
        entriesSuffix: "条",
        authors: "作者",
        venue: "期刊 / 出版方",
        published: "发表时间",
        index: "分区",
        copy: "复制全部",
        copied: "已复制",
        download: "下载 TXT",
        close: "关闭",
        footer: "来自 haoxiangluo.github.io/publications",
        sep: "："
      }
    : {
        title: "Export Publications",
        hint: "Enter the password to view and export the full publication summary.",
        password: "Password",
        unlock: "Unlock",
        cancel: "Cancel",
        wrong: "Incorrect password. Please try again.",
        summaryTitle: "Publications Summary",
        generatedPrefix: "Generated on",
        entriesSuffix: "entries",
        authors: "Authors",
        venue: "Journal / Publisher",
        published: "Published",
        index: "Index",
        copy: "Copy All",
        copied: "Copied!",
        download: "Download TXT",
        close: "Close",
        footer: "From haoxiangluo.github.io/publications",
        sep: ": "
      };

  var overlay = null;
  var dialog = null;
  var step1 = null;
  var step2 = null;
  var input = null;
  var errorEl = null;
  var listEl = null;
  var generatedEl = null;
  var copyBtn = null;
  var lastFocus = null;
  var plainText = "";
  var copiedTimer = null;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* Collect entries from the publication cards so the export always
     mirrors the page content. */
  function collectEntries() {
    var cards = Array.prototype.slice.call(document.querySelectorAll(".publication-card"));
    return cards.map(function (card) {
      var titleEl = card.querySelector("h3");
      var rankEl = card.querySelector(".publication-badge--rank");
      var venueEl = card.querySelector(".publication-meta em");
      var metaEl = card.querySelector(".publication-meta");
      return {
        title: titleEl ? titleEl.textContent.trim() : "",
        rank: card.getAttribute("data-rank") || (rankEl ? rankEl.textContent.trim() : ""),
        venue: card.getAttribute("data-venue") || (venueEl ? venueEl.textContent.trim() : (metaEl ? metaEl.textContent.trim() : "")),
        date: card.getAttribute("data-date") || card.getAttribute("data-year") || "",
        authors: card.getAttribute("data-authors") || ""
      };
    });
  }

  function buildPlainText(entries) {
    var today = new Date();
    var stamp = today.getFullYear() + "-" + String(today.getMonth() + 1).padStart(2, "0") + "-" + String(today.getDate()).padStart(2, "0");
    var lines = [];
    lines.push(isZh ? "发表信息汇总（Haoxiang Luo）" : "Publications Summary (Haoxiang Luo)");
    lines.push(t.generatedPrefix + " " + stamp + " · " + entries.length + " " + t.entriesSuffix);
    lines.push("");
    entries.forEach(function (entry, i) {
      lines.push("[" + (i + 1) + "] " + entry.title);
      lines.push("    " + t.authors + ": " + entry.authors);
      lines.push("    " + t.venue + ": " + entry.venue + (entry.rank ? " (" + entry.rank + ")" : ""));
      lines.push("    " + t.published + ": " + entry.date);
      lines.push("");
    });
    return lines.join("\n");
  }

  function renderEntries(entries) {
    listEl.innerHTML = entries.map(function (entry, i) {
      return (
        "<li>" +
        "<p class=\"pub-export-entry__title\">" + escapeHtml(entry.title) + "</p>" +
        "<p class=\"pub-export-entry__meta\">" +
        escapeHtml(t.authors) + t.sep + escapeHtml(entry.authors) + "<br>" +
        escapeHtml(t.venue) + t.sep + escapeHtml(entry.venue) +
        (entry.rank ? " <span class=\"pub-export-entry__rank\">" + escapeHtml(entry.rank) + "</span>" : "") + "<br>" +
        escapeHtml(t.published) + t.sep + escapeHtml(entry.date) +
        "</p>" +
        "</li>"
      );
    }).join("");
  }

  function buildModal() {
    overlay = document.createElement("div");
    overlay.className = "pub-export-overlay";
    overlay.hidden = true;
    overlay.innerHTML =
      "<div class=\"pub-export-dialog\" role=\"dialog\" aria-modal=\"true\" aria-label=\"" + escapeHtml(t.title) + "\">" +
      "<button type=\"button\" class=\"pub-export-close\" aria-label=\"" + escapeHtml(t.close) + "\">&times;</button>" +
      "<div class=\"pub-export-step pub-export-step--auth\">" +
      "<h3>" + escapeHtml(t.title) + "</h3>" +
      "<p class=\"pub-export-hint\">" + escapeHtml(t.hint) + "</p>" +
      "<label class=\"pub-export-label\">" + escapeHtml(t.password) +
      "<input type=\"password\" class=\"pub-export-input\" autocomplete=\"off\">" +
      "</label>" +
      "<p class=\"pub-export-error\" hidden></p>" +
      "<div class=\"pub-export-actions\">" +
      "<button type=\"button\" class=\"pub-export-btn-ui\" data-action=\"cancel\">" + escapeHtml(t.cancel) + "</button>" +
      "<button type=\"button\" class=\"pub-export-btn-ui pub-export-btn-ui--primary\" data-action=\"unlock\">" + escapeHtml(t.unlock) + "</button>" +
      "</div>" +
      "</div>" +
      "<div class=\"pub-export-step pub-export-step--summary\" hidden>" +
      "<h3>" + escapeHtml(t.summaryTitle) + "</h3>" +
      "<p class=\"pub-export-generated\"></p>" +
      "<ol class=\"pub-export-list\"></ol>" +
      "<p class=\"pub-export-footer\">" + escapeHtml(t.footer) + "</p>" +
      "<div class=\"pub-export-actions\">" +
      "<button type=\"button\" class=\"pub-export-btn-ui\" data-action=\"download\">" + escapeHtml(t.download) + "</button>" +
      "<button type=\"button\" class=\"pub-export-btn-ui\" data-action=\"copy\">" + escapeHtml(t.copy) + "</button>" +
      "<button type=\"button\" class=\"pub-export-btn-ui pub-export-btn-ui--primary\" data-action=\"close\">" + escapeHtml(t.close) + "</button>" +
      "</div>" +
      "</div>" +
      "</div>";
    document.body.appendChild(overlay);

    dialog = overlay.querySelector(".pub-export-dialog");
    step1 = overlay.querySelector(".pub-export-step--auth");
    step2 = overlay.querySelector(".pub-export-step--summary");
    input = overlay.querySelector(".pub-export-input");
    errorEl = overlay.querySelector(".pub-export-error");
    listEl = overlay.querySelector(".pub-export-list");
    generatedEl = overlay.querySelector(".pub-export-generated");
    copyBtn = overlay.querySelector("[data-action=\"copy\"]");

    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) close();
    });

    dialog.addEventListener("click", function (event) {
      var actionEl = event.target.closest("[data-action]");
      if (!actionEl) return;
      var action = actionEl.getAttribute("data-action");
      if (action === "cancel" || action === "close") close();
      if (action === "unlock") tryUnlock();
      if (action === "copy") copyAll();
      if (action === "download") downloadTxt();
    });

    dialog.querySelector(".pub-export-close").addEventListener("click", close);

    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") tryUnlock();
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !overlay.hidden) close();
    });
  }

  function tryUnlock() {
    if (input.value === PASSWORD) {
      var entries = collectEntries();
      plainText = buildPlainText(entries);
      renderEntries(entries);
      generatedEl.textContent = t.generatedPrefix + " " + new Date().toLocaleDateString() + " · " + entries.length + " " + t.entriesSuffix;
      errorEl.hidden = true;
      errorEl.textContent = "";
      input.value = "";
      step1.hidden = true;
      step2.hidden = false;
      dialog.classList.add("is-wide");
      dialog.scrollTop = 0;
    } else {
      errorEl.textContent = t.wrong;
      errorEl.hidden = false;
      dialog.classList.remove("is-error");
      void dialog.offsetWidth; /* restart animation */
      dialog.classList.add("is-error");
      input.select();
    }
  }

  function copyAll() {
    var done = function () {
      var previous = copyBtn.textContent;
      copyBtn.textContent = t.copied;
      if (copiedTimer) clearTimeout(copiedTimer);
      copiedTimer = setTimeout(function () { copyBtn.textContent = previous; }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(plainText).then(done, function () { fallbackCopy(); done(); });
    } else {
      fallbackCopy();
      done();
    }
  }

  function fallbackCopy() {
    var textarea = document.createElement("textarea");
    textarea.value = plainText;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    try { document.execCommand("copy"); } catch (err) { /* no-op */ }
    document.body.removeChild(textarea);
  }

  function downloadTxt() {
    var today = new Date();
    var stamp = today.getFullYear() + "-" + String(today.getMonth() + 1).padStart(2, "0") + "-" + String(today.getDate()).padStart(2, "0");
    var blob = new Blob(["\ufeff" + plainText], { type: "text/plain;charset=utf-8" });
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "publications-export-" + stamp + ".txt";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
  }

  function open() {
    if (!overlay) buildModal();
    lastFocus = document.activeElement;
    step1.hidden = false;
    step2.hidden = true;
    dialog.classList.remove("is-wide", "is-error");
    errorEl.hidden = true;
    input.value = "";
    overlay.hidden = false;
    document.body.style.overflow = "hidden";
    input.focus();
  }

  function close() {
    if (!overlay || overlay.hidden) return;
    overlay.hidden = true;
    document.body.style.overflow = "";
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  trigger.addEventListener("click", open);
})();
