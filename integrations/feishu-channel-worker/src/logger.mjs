import { redact, redactSecretsString } from './protocol.mjs';

export function createSafeLogger({ sink = console, contentLimit = 256, repeatWindowMs = 30000, secrets = [] } = {}) {
  const repeats = new Map();
  function emit(level, message, context = {}) {
    const safeMessage = String(message || '').slice(0, contentLimit);
    const safeContext = redact(context);
    const key = `${level}:${safeMessage}:${JSON.stringify(safeContext)}`;
    const now = Date.now();
    const previous = repeats.get(key) || { at: 0, count: 0 };
    previous.count += 1;
    if (now - previous.at < repeatWindowMs) {
      repeats.set(key, previous);
      return false;
    }
    previous.at = now;
    repeats.set(key, previous);
    const record = JSON.parse(redactSecretsString(JSON.stringify({ level, message: safeMessage, ...safeContext }), secrets));
    const method = typeof sink[level] === 'function' ? level : 'log';
    sink[method](JSON.stringify(record));
    return true;
  }
  return {
    debug: (message, context) => emit('debug', message, context),
    info: (message, context) => emit('info', message, context),
    warn: (message, context) => emit('warn', message, context),
    error: (message, context) => emit('error', message, context),
    repeatCount: (level, message, context = {}) => repeats.get(`${level}:${String(message || '').slice(0, contentLimit)}:${JSON.stringify(redact(context))}`)?.count || 0,
  };
}
