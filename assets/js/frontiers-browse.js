(function () {
  "use strict";

  var archive = document.querySelector(".frontiers-archive");
  if (!archive) return;
  var isChinese = document.querySelector("[data-date-filter]").dataset.language === "zh";
  var journals = archive.querySelectorAll("[data-frontier-journal]");

  document.addEventListener("frontiers-period-change", function (event) {
    journals.forEach(function (journal) {
      var matches = journal.querySelectorAll(".frontiers-paper:not([hidden])");
      var preview = journal.querySelector("[data-journal-preview]");
      var count = journal.querySelector("[data-journal-count]");
      journal.hidden = !matches.length && (event.detail.active || journal.dataset.frontierJournal === "other");
      journal.querySelector("[data-journal-empty]").hidden = matches.length > 0;
      count.textContent = matches.length + (isChinese ? " 篇" : (matches.length === 1 ? " article" : " articles"));
      preview.hidden = matches.length === 0;
      preview.textContent = matches.length ? matches[0].querySelector(".frontiers-paper__title").textContent : "";
    });
  });
}());
