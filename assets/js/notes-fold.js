(function () {
  "use strict";
  var layout = document.querySelector(".notes-tools-layout");
  if (!layout) return;
  var zh = document.documentElement.lang.toLowerCase().indexOf("zh") === 0;
  function button(label) {
    var el = document.createElement("button");
    el.type = "button";
    el.className = "notes-fold__button";
    el.setAttribute("aria-expanded", "false");
    el.textContent = label;
    return el;
  }
  function foldText(p) {
    var full = p.textContent.trim();
    var chars = Array.from(full);
    var cjk = (full.match(/[\u3400-\u9fff]/g) || []).length;
    var limit = cjk > 30 ? 100 : 220;
    if (chars.length <= limit) return;
    var brief = chars.slice(0, limit).join("").trim() + "…";
    var control = button(zh ? "展开全文" : "Read more");
    p.textContent = brief;
    p.insertAdjacentElement("afterend", control);
    control.addEventListener("click", function (event) {
      event.stopPropagation();
      var expanded = control.getAttribute("aria-expanded") === "true";
      p.textContent = expanded ? brief : full;
      control.setAttribute("aria-expanded", String(!expanded));
      control.textContent = expanded ? (zh ? "展开全文" : "Read more") : (zh ? "收起" : "Show less");
    });
  }
  function foldList(container, selector, count) {
    var children = Array.prototype.slice.call(container.querySelectorAll(selector));
    if (children.length <= count) return;
    var control = button("");
    container.insertAdjacentElement("afterend", control);
    function render() {
      var expanded = control.getAttribute("aria-expanded") === "true";
      children.forEach(function (child, index) { child.hidden = index >= count && !expanded; });
      control.textContent = expanded ? (zh ? "收起" : "Show less")
        : (zh ? "展开其余 " + (children.length - count) + " 项" : "Show " + (children.length - count) + " more");
    }
    control.addEventListener("click", function (event) {
      event.stopPropagation();
      control.setAttribute("aria-expanded", String(control.getAttribute("aria-expanded") !== "true"));
      render();
    });
    render();
  }
  layout.querySelectorAll(".notes-topic__desc, .skill-entry p").forEach(foldText);
  layout.querySelectorAll(".notes-topic__entries").forEach(function (list) { foldList(list, ":scope > li", 3); });
  layout.querySelectorAll(".skills-library__grid").forEach(function (grid) { foldList(grid, ":scope > .skill-entry", 4); });
}());
