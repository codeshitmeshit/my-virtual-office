(function () {
  const SUPPORTED_COMMANDS = new Set(['/new', '/compact']);

  function normalizeText(text) {
    return String(text || '').trim();
  }

  function classify(text, options = {}) {
    const value = normalizeText(text);
    if (!value || options.hasAttachments || !value.startsWith('/')) {
      return { kind: 'ordinary', text: value };
    }
    if (SUPPORTED_COMMANDS.has(value)) {
      return { kind: 'command', command: value, text: value };
    }
    return { kind: 'blocked', text: value };
  }

  function disabledMessage(command) {
    return `Slash command ${command} is disabled; message was not sent.`;
  }

  function blockedMessage(text) {
    const command = String(text || '').split(/\s+/, 1)[0] || '/';
    return `Unknown slash command ${command}; message was not sent.`;
  }

  window.ChatSlashGuard = Object.freeze({
    classify,
    disabledMessage,
    blockedMessage
  });
})();
