// The Safe-Until Clock. Every [data-clock] shows time left as text and every [data-clockbar]
// drains as the safe-until moment approaches. Both update each second with no page reload and
// carry a data-state of ok / soon / late, which the CSS turns into leaf / turmeric / chilli.
(function () {
  "use strict";

  var SOON = 2700; // under 45 minutes: turmeric
  var LATE = 900;  // under 15 minutes: chilli

  function stateFor(seconds) {
    if (seconds <= LATE) return "late";
    return seconds <= SOON ? "soon" : "ok";
  }

  function format(seconds) {
    var h = Math.floor(seconds / 3600);
    var m = Math.floor((seconds % 3600) / 60);
    var s = Math.floor(seconds % 60);
    if (h > 0) return h + "h " + (m < 10 ? "0" : "") + m + "m";
    return m + "m " + (s < 10 ? "0" : "") + s + "s";
  }

  // Sample clocks (the landing-page docket) are set relative to "now" so they always look alive.
  document.querySelectorAll("[data-demo-left]").forEach(function (el) {
    var now = Date.now() / 1000;
    var left = Number(el.getAttribute("data-demo-left")) * 60;
    var elapsed = Number(el.getAttribute("data-demo-elapsed") || 0) * 60;
    el.setAttribute("data-end", String(now + left));
    el.setAttribute("data-start", String(now - elapsed));
  });

  function tick() {
    var now = Date.now() / 1000;

    document.querySelectorAll("[data-clock]").forEach(function (el) {
      var left = Math.floor(Number(el.getAttribute("data-end")) - now);
      var time = el.querySelector(".fb-clock__time");
      var label = el.querySelector(".fb-clock__label");
      el.setAttribute("data-state", left <= 0 ? "late" : stateFor(left));
      if (time) time.textContent = left <= 0 ? "time is up" : format(left);
      if (label) label.textContent = left <= 0 ? "" : label.getAttribute("data-live") || "safe for";
    });

    document.querySelectorAll("[data-clockbar]").forEach(function (bar) {
      var start = Number(bar.getAttribute("data-start"));
      var end = Number(bar.getAttribute("data-end"));
      var total = Math.max(1, end - start);
      var left = end - now;
      var pct = Math.max(0, Math.min(100, (left / total) * 100));
      bar.setAttribute("data-state", left <= 0 ? "late" : stateFor(left));
      if (bar.firstElementChild) bar.firstElementChild.style.width = pct + "%";
    });
  }

  tick();
  setInterval(tick, 1000);
})();
