// Small, dependency-free helpers shared by every page.
(function () {
  "use strict";

  // ---- flash messages: close button + success messages fade away on their own -----------------
  document.querySelectorAll(".fb-flash").forEach(function (flash) {
    var button = flash.querySelector("button");
    if (button) button.addEventListener("click", function () { flash.remove(); });
    if (flash.classList.contains("fb-flash--success")) setTimeout(function () { flash.remove(); }, 7000);
  });

  // ---- filter panel: always open on wide screens, collapsible on phones -------------------------
  var wide = window.matchMedia("(min-width: 768px)");
  document.querySelectorAll("details.fb-filters").forEach(function (panel) {
    function sync() { if (wide.matches) panel.open = true; }
    sync();
    if (wide.addEventListener) wide.addEventListener("change", sync);
  });

  // ---- "add another food item" for the listing form ------------------------------------------
  var addButton = document.querySelector("[data-formset-add]");
  var template = document.getElementById("fb-item-template");
  if (addButton && template) {
    var holder = document.getElementById("fb-item-rows");
    var total = document.getElementById("id_items-TOTAL_FORMS");

    function bindRemove(row) {
      var remove = row.querySelector("[data-row-remove]");
      if (!remove) return;
      remove.addEventListener("click", function () {
        row.remove();
        renumber();
      });
    }

    function renumber() {
      var rows = holder.querySelectorAll(".fb-itemrow");
      rows.forEach(function (row, index) {
        row.querySelectorAll("[name], [id], label[for]").forEach(function (node) {
          ["name", "id", "for"].forEach(function (attr) {
            var value = node.getAttribute(attr);
            if (value) node.setAttribute(attr, value.replace(/items-\d+-/, "items-" + index + "-"));
          });
        });
        var title = row.querySelector("[data-row-title]");
        if (title) title.textContent = "Item " + (index + 1);
      });
      total.value = rows.length;
    }

    addButton.addEventListener("click", function () {
      var index = holder.querySelectorAll(".fb-itemrow").length;
      var html = template.innerHTML.replace(/__prefix__/g, String(index));
      var wrapper = document.createElement("div");
      wrapper.innerHTML = html.trim();
      var row = wrapper.firstElementChild;
      holder.appendChild(row);
      bindRemove(row);
      renumber();
      var first = row.querySelector("input[type=text]");
      if (first) first.focus();
    });

    holder.querySelectorAll(".fb-itemrow").forEach(bindRemove);
  }
})();
