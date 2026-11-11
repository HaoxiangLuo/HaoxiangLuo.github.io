/* Hide notices only when the source supplies a valid, past deadline. */
(function () {
  "use strict";
  function shanghaiDate() {
    var parts = new Intl.DateTimeFormat("en-CA", {timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit"}).formatToParts(new Date());
    var values = {};
    parts.forEach(function (part) { values[part.type] = part.value; });
    return values.year + "-" + values.month + "-" + values.day;
  }
  function validDate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    var parsed = new Date(value + "T00:00:00Z");
    return !isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
  }
  var today;
  try { today = shanghaiDate(); } catch (error) { return; }
  document.querySelectorAll("[data-opp-deadline]").forEach(function (item) {
    var deadline = item.getAttribute("data-opp-deadline");
    if (validDate(deadline) && deadline < today) {
      item.setAttribute("data-opp-expired", "true");
      item.hidden = true;
    }
  });
}());
