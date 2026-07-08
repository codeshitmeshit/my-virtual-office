(function (root) {
  'use strict';

  function buildBrowserViewerUrl(viewerUrl, pageUrl) {
    var url = new URL(viewerUrl, pageUrl);
    var shouldUseLocalProxy = url.username || url.password;
    if (shouldUseLocalProxy && /^https?:$/.test(url.protocol)) {
      return new URL('/browser-viewer', pageUrl).toString();
    }
    if (!url.searchParams.has('path')) {
      var basePath = url.pathname.replace(/^\/+|\/+$/g, '');
      url.searchParams.set('path', (basePath ? basePath + '/' : '') + 'websockify');
    }
    if (!url.searchParams.has('password') && url.password) {
      url.searchParams.set('password', url.password);
    }
    if (!url.searchParams.has('resize')) url.searchParams.set('resize', 'scale');
    if (!url.searchParams.has('autoconnect')) url.searchParams.set('autoconnect', '1');
    if (!url.searchParams.has('_vo_embed')) url.searchParams.set('_vo_embed', '1');
    return url.toString();
  }

  root.buildBrowserViewerUrl = buildBrowserViewerUrl;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { buildBrowserViewerUrl: buildBrowserViewerUrl };
  }
})(typeof window !== 'undefined' ? window : globalThis);
