// Progressive enhancement for the handover code screens. Without JavaScript the plain
// 6-digit text box and the server-side checks still work; this only makes it nicer.
(function () {
  "use strict";
  var LENGTH = 6;

  // ---- 1. Six separate digit boxes that feed the real <input name="code"> -------------------
  document.querySelectorAll("[data-code-boxes]").forEach(function (form) {
    var real = form.querySelector(".fb-code-input");
    var holder = form.querySelector("[data-code-boxes-holder]");
    var submit = form.querySelector("[type=submit]");
    if (!real || !holder) return;

    var boxes = [];
    for (var i = 0; i < LENGTH; i++) {
      var box = document.createElement("input");
      box.type = "text";
      box.inputMode = "numeric";
      box.maxLength = 1;
      box.autocomplete = i === 0 ? "one-time-code" : "off";
      box.placeholder = " ";
      box.setAttribute("aria-label", "Digit " + (i + 1) + " of " + LENGTH);
      if (real.disabled) box.disabled = true;
      holder.appendChild(box);
      boxes.push(box);
    }
    form.classList.add("js-code-boxes");

    function sync() {
      real.value = boxes.map(function (b) { return b.value; }).join("");
      if (submit && !submit.hasAttribute("data-locked")) submit.disabled = real.value.length !== LENGTH;
    }
    function fill(digits, start) {
      for (var k = 0; k < digits.length && start + k < LENGTH; k++) boxes[start + k].value = digits[k];
      var next = Math.min(start + digits.length, LENGTH - 1);
      boxes[next].focus();
      sync();
    }

    boxes.forEach(function (box, index) {
      box.addEventListener("input", function () {
        var digits = box.value.replace(/\D/g, "");
        box.value = "";
        if (digits) fill(digits, index);
        else sync();
      });
      box.addEventListener("keydown", function (e) {
        if (e.key === "Backspace" && !box.value && index > 0) {
          boxes[index - 1].value = "";
          boxes[index - 1].focus();
          sync();
        } else if (e.key === "ArrowLeft" && index > 0) boxes[index - 1].focus();
        else if (e.key === "ArrowRight" && index < LENGTH - 1) boxes[index + 1].focus();
      });
      box.addEventListener("paste", function (e) {
        var text = (e.clipboardData || window.clipboardData).getData("text").replace(/\D/g, "");
        if (!text) return;
        e.preventDefault();
        fill(text.slice(0, LENGTH), 0);
      });
      box.addEventListener("focus", function () { box.select(); });
    });

    sync();
    if (!real.disabled) boxes[0].focus();
  });

  // ---- 2. Live countdown to the code's expiry (= the food's safe-until time) ----------------
  var timers = Array.prototype.slice.call(document.querySelectorAll("[data-countdown]"));
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function tick() {
    var now = Date.now();
    timers.forEach(function (el) {
      // data-countdown holds the expiry as epoch seconds (parses identically in every browser)
      var left = Math.floor((Number(el.getAttribute("data-countdown")) * 1000 - now) / 1000);
      if (left <= 0) {
        el.textContent = "expired";
        el.classList.add("fb-timer--done");
        if (!el.hasAttribute("data-expired")) {
          el.setAttribute("data-expired", "1");
          // lock the entry form on this page so nobody types into an expired code
          document.querySelectorAll("[data-disable-on-expiry]").forEach(function (node) {
            node.disabled = true;
            node.setAttribute("data-locked", "1");
          });
        }
        return;
      }
      var h = Math.floor(left / 3600), m = Math.floor((left % 3600) / 60), s = left % 60;
      el.textContent = (h ? h + "h " : "") + pad(m) + "m " + pad(s) + "s left";
      el.classList.toggle("fb-timer--low", left < 900);
    });
  }
  if (timers.length) { tick(); setInterval(tick, 1000); }

  // ---- 3. Copy-to-clipboard button on the NGO's code card -----------------------------------
  document.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var text = button.getAttribute("data-copy");
      var done = function () {
        var old = button.textContent;
        button.textContent = "Copied";
        setTimeout(function () { button.textContent = old; }, 1500);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {});
      }
    });
  });
})();
