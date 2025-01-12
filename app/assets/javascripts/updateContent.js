(function (Modules) {
  "use strict";

  var queues = {};
  //var dd = new diffDOM();
  var dd = new window.DiffDOM();

  var getRenderer = ($component) => (response) => {
    var contentStr = $(response[$component.data("key")]).get(0);
    return dd.apply($component.get(0), dd.diff($component.get(0), contentStr));
  };

  var getQueue = (resource) => (queues[resource] = queues[resource] || []);

  var flushQueue = function (queue, response) {
    while (queue.length) queue.shift()(response);
  };

  var clearQueue = (queue) => (queue.length = 0);

  var poll = function (renderer, resource, queue, interval, form) {
    if (document.visibilityState !== "hidden" && queue.push(renderer) === 1)
      $.ajax(resource, {
        method: form ? "post" : "get",
        data: form ? $("#" + form).serialize() : {},
      })
        .done((response) => {
          flushQueue(queue, response);
          if (response.stop === 1) {
            poll = function () {};
          }
          window.formatAllDates();
        })
        .fail(() => (poll = function () {}));

    setTimeout(() => poll.apply(window, arguments), interval);
  };

  Modules.UpdateContent = function () {
    this.start = (component) =>
      poll(
        getRenderer($(component)),
        $(component).data("resource"),
        getQueue($(component).data("resource")),
        ($(component).data("interval-seconds") || 1.5) * 1000,
        $(component).data("form")
      );
  };
})(window.GOVUK.Modules);
