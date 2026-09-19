(function () {
  "use strict";

  var grid = document.querySelector(".notes-grid");
  if (!grid) return;

  var cards = Array.prototype.slice.call(grid.querySelectorAll(".notes-topic"));
  if (!cards.length) return;

  var labels = {
    open: grid.getAttribute("data-label-open") || "Open",
    close: grid.getAttribute("data-label-close") || "Close"
  };

  var DURATION = 380;

  function parts(card) {
    return {
      toggle: card.querySelector(".notes-topic__toggle"),
      cueText: card.querySelector(".notes-topic__cue-text"),
      panel: card.querySelector(".notes-topic__panel")
    };
  }

  function paint(card, open) {
    var p = parts(card);
    card.classList.toggle("is-open", open);
    if (p.toggle) p.toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (p.cueText) p.cueText.textContent = open ? labels.close : labels.open;
    grid.classList.toggle("has-open-topic", cards.some(function (topic) {
      return topic.classList.contains("is-open");
    }));
  }

  function open(card) {
    var p = parts(card);
    if (!p.panel || card.classList.contains("is-open")) return;
    cards.forEach(function (other) {
      if (other !== card && other.classList.contains("is-open")) close(other);
    });
    if (p.panel._closeTimer) {
      window.clearTimeout(p.panel._closeTimer);
      p.panel._closeTimer = null;
    }
    p.panel.hidden = false;
    // Force a reflow so the height transition runs from the collapsed state.
    void p.panel.offsetHeight;
    paint(card, true);
  }

  function close(card) {
    var p = parts(card);
    if (!p.panel || !card.classList.contains("is-open")) return;
    paint(card, false);
    p.panel._closeTimer = window.setTimeout(function () {
      // Only hide if the card has not been reopened in the meantime.
      if (!card.classList.contains("is-open")) p.panel.hidden = true;
      p.panel._closeTimer = null;
    }, DURATION);
  }

  function toggle(card) {
    if (card.classList.contains("is-open")) close(card);
    else open(card);
  }

  cards.forEach(function (card) {
    var p = parts(card);
    if (!p.panel) return;

    // Start collapsed, but keep the content reachable when scripting is unavailable.
    p.panel.hidden = true;

    if (p.toggle) {
      p.toggle.addEventListener("click", function (event) {
        event.preventDefault();
        toggle(card);
      });
    }

    card.addEventListener("click", function (event) {
      if (event.target.closest("a")) return;
      if (event.target.closest(".notes-topic__panel")) return;
      if (event.target.closest(".notes-topic__toggle")) return;
      toggle(card);
    });

    card.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      if (!card.classList.contains("is-open")) return;
      close(card);
      if (p.toggle) p.toggle.focus();
    });
  });

  // Deep link support: /zh/study-notes/#notes-panel-global opens that card.
  function openFromHash() {
    var id = window.location.hash.replace(/^#/, "");
    if (!id) return;
    cards.forEach(function (card) {
      var p = parts(card);
      if (!p.panel || p.panel.id !== id) return;
      open(card);
      // Scroll the window itself instead of calling scrollIntoView(): the card
      // and its panel are overflow:hidden containers, so scrollIntoView() would
      // scroll them internally and clip the card header (the "01" number).
      var top = card.getBoundingClientRect().top + window.pageYOffset - 96;
      window.scrollTo({ top: Math.max(top, 0), behavior: "smooth" });
    });
  }

  openFromHash();
  window.addEventListener("hashchange", openFromHash);
}());
