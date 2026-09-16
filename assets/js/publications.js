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
