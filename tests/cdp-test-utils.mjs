export const cdpURL = (process.env.VO_CDP_URL || 'http://127.0.0.1:9224').replace(/\/$/, '');
export const appURL = (process.env.VO_APP_URL || 'http://127.0.0.1:8090/').replace(/\/?$/, '/');
export const apiURL = (process.env.VO_API_URL || appURL).replace(/\/$/, '');
export const liveURL = (process.env.VO_LIVE_URL || appURL).replace(/\/?$/, '/');

export async function cdpJson(path, options = {}) {
  const normalized = String(path || '').startsWith('/') ? path : `/${path}`;
  try {
    const res = await fetch(`${cdpURL}${normalized}`, options);
    return await res.json();
  } catch (error) {
    throw new Error(`CDP is unavailable at ${cdpURL}. Run ./start.sh --browser, start local Chrome with remote debugging enabled, or set VO_CDP_URL to another reachable Chrome DevTools endpoint. ${error.message || error}`);
  }
}

export function cdpNewPageUrl(url) {
  return `/json/new?${encodeURIComponent(url)}`;
}

export async function createCdpPage(url = 'about:blank') {
  return cdpJson(cdpNewPageUrl(url), { method: 'PUT' });
}

export function closeCdpPage(pageInfo) {
  if (!pageInfo || !pageInfo.id) return Promise.resolve();
  return fetch(`${cdpURL}/json/close/${encodeURIComponent(pageInfo.id)}`).catch(() => {});
}

export async function cdpVersion() {
  return cdpJson('/json/version');
}
