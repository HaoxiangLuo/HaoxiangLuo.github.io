(function () {
  "use strict";
  var timeline = document.querySelector(".site-timeline");
  if (!timeline) return;
  var zh = document.documentElement.lang.toLowerCase().indexOf("zh") === 0;
  var queued = false;

  function foldStory(story) {
    if (story.dataset.foldReady) return;
    story.dataset.foldReady = "true";
    var full = story.textContent.trim();
    var chars = Array.from(full);
    var cjk = (full.match(/[\u3400-\u9fff]/g) || []).length;
    var limit = cjk > 30 ? 100 : 220;
    if (chars.length <= limit) return;
    var shortText = chars.slice(0, limit).join("").trim() + "…";
    var button = document.createElement("button");
    button.type = "button";
    button.className = "site-log-fold__story-button";
    button.setAttribute("aria-expanded", "false");
    button.textContent = zh ? "展开全文" : "Read more";
    story.textContent = shortText;
    story.insertAdjacentElement("afterend", button);
    button.addEventListener("click", function () {
      var expanded = button.getAttribute("aria-expanded") === "true";
      story.textContent = expanded ? shortText : full;
      button.setAttribute("aria-expanded", String(!expanded));
      button.textContent = expanded ? (zh ? "展开全文" : "Read more") : (zh ? "收起" : "Show less");
    });
  }

  function refreshDay(day) {
    var items = day.querySelector(".site-log-day__items");
    if (!items) return;
    var entries = Array.prototype.slice.call(items.querySelectorAll(":scope > .site-log-entry"));
    entries.forEach(function (entry) {
      var story = entry.querySelector(".site-log-entry__story");
      if (story) foldStory(story);
    });
    var card = day.querySelector(".site-log-day__card");
    var button = card.querySelector(".site-log-fold__day-button");
    if (entries.length <= 3 && !button) return;
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.className = "site-log-fold__day-button";
      button.setAttribute("aria-expanded", "false");
      card.appendChild(button);
      button.addEventListener("click", function () {
        button.setAttribute("aria-expanded", String(button.getAttribute("aria-expanded") !== "true"));
        refreshDay(day);
      });
    }
    var expanded = button.getAttribute("aria-expanded") === "true";
    entries.forEach(function (entry, index) { entry.hidden = index >= 3 && !expanded; });
    button.hidden = entries.length <= 3;
    button.textContent = expanded ? (zh ? "收起更新" : "Show fewer updates")
      : (zh ? "展开其余 " + (entries.length - 3) + " 条更新" : "Show " + (entries.length - 3) + " more updates");
  }

  function refresh() {
    queued = false;
    timeline.querySelectorAll(".site-log-day").forEach(refreshDay);
  }
  refresh();
  new MutationObserver(function (mutations) {
    var hasEntries = mutations.some(function (mutation) {
      return Array.prototype.some.call(mutation.addedNodes, function (node) {
        return node.nodeType === 1 && (node.matches(".site-log-day, .site-log-entry") ||
          node.querySelector(".site-log-day, .site-log-entry"));
      });
    });
    if (hasEntries && !queued) {
      queued = true;
      requestAnimationFrame(refresh);
    }
  }).observe(timeline, { childList: true, subtree: true });
}());
