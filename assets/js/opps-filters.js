/* Filter chips for the United Nations shortlist on the Opportunities page.

   Each card carries what it is as data attributes (data-org, data-areas,
   data-mode, data-region, data-status, data-score); each chip carries the one
   value it stands for. Nothing else about the page is assumed here, so the bar
   can be dropped into either language without configuration.

   The bar starts hidden and is revealed by this script: without JavaScript the
   chips would filter nothing, and a control that does nothing is worse than no
   control at all.
*/
(function () {
  "use strict";

  function selected(filters, key) {
    return filters[key] || [];
  }

  function matches(card, filters) {
    var score = Number(card.getAttribute("data-score") || 0);
    var checks = [
      ["org", card.getAttribute("data-org")],
      ["mode", card.getAttribute("data-mode")],
      ["region", card.getAttribute("data-region")],
      ["status", card.getAttribute("data-status")],
    ];
    for (var i = 0; i < checks.length; i += 1) {
      var wanted = selected(filters, checks[i][0]);
      if (wanted.length && wanted.indexOf(checks[i][1]) === -1) {
        return false;
      }
    }
    var areas = (card.getAttribute("data-areas") || "").split(/\s+/);
    var wantedAreas = selected(filters, "areas");
    if (wantedAreas.length && !wantedAreas.some(function (area) {
      return areas.indexOf(area) !== -1;
    })) {
      return false;
    }
    var bands = selected(filters, "score").map(Number).filter(function (n) {
      return !isNaN(n);
    });
    // The lowest chosen band wins: "80+" also shows everything above it.
    if (bands.length && score < Math.min.apply(null, bands)) {
      return false;
    }
    return true;
  }

  function apply(root) {
    var filters = {};
    var chips = root.querySelectorAll("[data-filter][aria-pressed='true']");
    Array.prototype.forEach.call(chips, function (chip) {
      var key = chip.getAttribute("data-filter");
      filters[key] = (filters[key] || []).concat(chip.getAttribute("data-value"));
    });
    var cards = document.querySelectorAll("[data-opp]");
    var shown = 0;
    Array.prototype.forEach.call(cards, function (card) {
      var visible = matches(card, filters);
      card.hidden = !visible;
      if (visible) {
        shown += 1;
      }
    });
    var counter = root.querySelector("[data-opps-count]");
    if (counter) {
      counter.textContent = shown + " / " + cards.length;
    }
    document.querySelectorAll("[data-opps-empty]").forEach(function (note) {
      note.hidden = shown !== 0;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-opps-filters]");
    if (!root) {
      return;
    }
    root.hidden = false;
    root.addEventListener("click", function (event) {
      var chip = event.target.closest("[data-filter]");
      if (chip) {
        var on = chip.getAttribute("aria-pressed") === "true";
        chip.setAttribute("aria-pressed", on ? "false" : "true");
        apply(root);
        return;
      }
      if (event.target.closest("[data-opps-reset]")) {
        Array.prototype.forEach.call(root.querySelectorAll("[data-filter]"), function (button) {
          button.setAttribute("aria-pressed", "false");
        });
        apply(root);
      }
    });
    apply(root);
  });
})();
