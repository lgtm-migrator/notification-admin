// From
// https://github.com/alphagov/govuk_elements/blob/4926897dc7734db2fc5e5ebb6acdc97f86e22e50/public/javascripts/vendor/details.polyfill.js
//
// ---
//
// <details> polyfill
// http://caniuse.com/#feat=details

// FF Support for HTML5's <details> and <summary>
// https://bugzilla.mozilla.org/show_bug.cgi?id=591737

// http://www.sitepoint.com/fixing-the-details-element/

(function () {
  "use strict";

  var NATIVE_DETAILS =
    typeof document.createElement("details").open === "boolean";

  // Add event construct for modern browsers or IE
  // which fires the callback with a pre-converted target reference
  function addEvent(node, type, callback) {
    if (node.addEventListener) {
      node.addEventListener(
        type,
        function (e) {
          callback(e, e.target);
        },
        false
      );
    } else if (node.attachEvent) {
      node.attachEvent("on" + type, function (e) {
        callback(e, e.srcElement);
      });
    }
  }

  // Handle cross-modal click events
  function addClickEvent(node, callback) {
    // Prevent space(32) from scrolling the page
    addEvent(node, "keypress", function (e, target) {
      if (target.nodeName === "SUMMARY") {
        if (e.keyCode === 32) {
          if (e.preventDefault) {
            e.preventDefault();
          } else {
            e.returnValue = false;
          }
        }
      }
    });
    // When the key comes up - check if it is enter(13) or space(32)
    addEvent(node, "keyup", function (e, target) {
      if (e.keyCode === 13 || e.keyCode === 32) {
        callback(e, target);
      }
    });
    addEvent(node, "mouseup", function (e, target) {
      callback(e, target);
    });
  }

  // Get the nearest ancestor element of a node that matches a given tag name
  function getAncestor(node, match) {
    do {
      if (!node || node.nodeName.toLowerCase() === match) {
        break;
      }
    } while ((node = node.parentNode));

    return node;
  }

  // Create a started flag so we can prevent the initialisation
  // function firing from both DOMContentLoaded and window.onload
  var started = false;

  // Initialisation function
  function addDetailsPolyfill(list) {
    // If this has already happened, just return
    // else set the flag so it doesn't happen again
    if (started) {
      return;
    }
    started = true;

    // Get the collection of details elements, but if that's empty
    // then we don't need to bother with the rest of the scripting
    if ((list = document.getElementsByTagName("details")).length === 0) {
      return;
    }

    // else iterate through them to apply their initial state
    var n = list.length,
      i = 0;
    for (i; i < n; i++) {
      var details = list[i];

      // Save shortcuts to the inner summary and content elements
      details.__summary = details.getElementsByTagName("summary").item(0);
      details.__content = details.getElementsByTagName("div").item(0);
      details.__interactive =
        details.__content.querySelectorAll("a, input, button");

      // If the content doesn't have an ID, assign it one now
      // which we'll need for the summary's aria-controls assignment
      if (!details.__content.id) {
        details.__content.id = "details-content-" + i;
      }

      // Add ARIA role="group" to details
      details.setAttribute("role", "group");

      // Add role=button to summary
      details.__summary.setAttribute("role", "button");

      // Add aria-controls
      details.__summary.setAttribute("aria-controls", details.__content.id);

      // Set tabIndex so the summary is keyboard accessible for non-native elements
      // http://www.saliences.com/browserBugs/tabIndex.html
      if (!NATIVE_DETAILS) {
        details.__summary.tabIndex = 0;
      }

      // Detect initial open state
      var openAttr = details.getAttribute("open") !== null;
      if (openAttr === true) {
        details.__summary.setAttribute("aria-expanded", "true");
        details.__content.setAttribute("aria-hidden", "false");
        details.__interactive.forEach((element) => {
          element.setAttribute("tabIndex", 0);
        });
      } else {
        details.__summary.setAttribute("aria-expanded", "false");
        details.__content.setAttribute("aria-hidden", "true");
        details.__interactive.forEach((element) => {
          element.setAttribute("tabIndex", -1);
        });
        if (!NATIVE_DETAILS) {
          details.__content.style.display = "none";
        }
      }

      // Create a circular reference from the summary back to its
      // parent details element, for convenience in the click handler
      details.__summary.__details = details;

      // If this is not a native implementation, create an arrow
      // inside the summary

      var twisty = document.createElement("i");

      if (openAttr === true) {
        twisty.className = "arrow arrow-open";
        twisty.appendChild(document.createTextNode("\u25bc"));
      } else {
        twisty.className = "arrow arrow-closed";
        twisty.appendChild(document.createTextNode("\u25ba"));
      }

      details.__summary.__twisty = details.__summary.insertBefore(
        twisty,
        details.__summary.firstChild
      );
      details.__summary.__twisty.setAttribute("aria-hidden", "true");
    }

    // Define a statechange function that updates aria-expanded and style.display
    // Also update the arrow position
    function statechange(summary) {
      var expanded =
        summary.__details.__summary.getAttribute("aria-expanded") === "true";
      var hidden =
        summary.__details.__content.getAttribute("aria-hidden") === "true";

      summary.__details.__summary.setAttribute(
        "aria-expanded",
        expanded ? "false" : "true"
      );
      summary.__details.__content.setAttribute(
        "aria-hidden",
        hidden ? "false" : "true"
      );
      summary.__details.__interactive.forEach((element) => {
        element.setAttribute("tabIndex", hidden ? 0 : -1);
      });

      if (!NATIVE_DETAILS) {
        summary.__details.__content.style.display = expanded ? "none" : "";

        var hasOpenAttr = summary.__details.getAttribute("open") !== null;
        if (!hasOpenAttr) {
          summary.__details.setAttribute("open", "open");
        } else {
          summary.__details.removeAttribute("open");
        }
      }

      if (summary.__twisty) {
        summary.__twisty.firstChild.nodeValue = expanded ? "\u25ba" : "\u25bc";
        summary.__twisty.setAttribute(
          "class",
          expanded ? "arrow arrow-closed" : "arrow arrow-open"
        );
      }

      return true;
    }

    // Bind a click event to handle summary elements
    addClickEvent(document, function (e, summary) {
      if (!(summary = getAncestor(summary, "summary"))) {
        return true;
      }
      return statechange(summary);
    });
  }

  // Bind two load events for modern and older browsers
  // If the first one fires it will set a flag to block the second one
  // but if it's not supported then the second one will fire
  addEvent(document, "DOMContentLoaded", addDetailsPolyfill);
  addEvent(window, "load", addDetailsPolyfill);
})();
