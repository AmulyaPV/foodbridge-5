// Small, dependency-free helpers shared by every page.
(function () {
  "use strict";

  // ---- CSRF helper for AJAX/fetch calls ---------------------------------------
  function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      var cookies = document.cookie.split(";");
      for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + "=")) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
  window.fbGetCsrfToken = function () {
    var tokenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (tokenInput && tokenInput.value) return tokenInput.value;
    return getCookie("csrftoken") || "";
  };

  // ---- Reliable fetch wrapper with cold-start & error handling ----------------
  window.fbFetch = function (url, options) {
    options = options || {};
    options.credentials = options.credentials || "same-origin";
    options.headers = options.headers || {};
    if (!options.headers["X-Requested-With"]) {
      options.headers["X-Requested-With"] = "XMLHttpRequest";
    }
    if (!options.headers["Accept"]) {
      options.headers["Accept"] = "application/json";
    }
    if (options.method && options.method.toUpperCase() === "POST" && !options.headers["X-CSRFToken"]) {
      options.headers["X-CSRFToken"] = window.fbGetCsrfToken();
    }
    return fetch(url, options).then(function (res) {
      if (!res.ok) {
        if (res.status === 401) {
          throw new Error("Authentication required. Please log in.");
        }
        if (res.status === 403) {
          throw new Error("Action not permitted.");
        }
        if (res.status >= 500) {
          throw new Error("Server error (" + res.status + "). Instance may be starting up, please retry.");
        }
        throw new Error("Request failed with status " + res.status);
      }
      return res.json();
    });
  };

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
