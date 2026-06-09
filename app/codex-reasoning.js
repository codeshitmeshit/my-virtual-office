(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.CodexReasoning = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function createState() {
    return { text: '', pendingBoundary: false, eventIds: new Set() };
  }

  function applyEvent(state, event) {
    const next = state || createState();
    if (event.id && next.eventIds.has(event.id)) return next;
    if (event.id) next.eventIds.add(event.id);

    const incoming = String(event.text || event.output || '');
    if (event.replace && incoming.trim()) {
      next.text = incoming;
      next.pendingBoundary = false;
      return next;
    }
    if (event.boundary && next.text.trim()) next.pendingBoundary = true;
    if (incoming) {
      if (next.pendingBoundary && !next.text.endsWith('\n\n')) next.text += '\n\n';
      next.text += incoming;
      next.pendingBoundary = false;
    }
    return next;
  }

  return { createState, applyEvent };
});
