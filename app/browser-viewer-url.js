(function (root) {
  'use strict';

  function buildBrowserViewerUrl(viewerUrl, pageUrl) {
    var url = new URL(viewerUrl, pageUrl);
    if (!url.searchParams.has('path')) {
      var basePath = url.pathname.replace(/^\/+|\/+$/g, '');
      url.searchParams.set('path', (basePath ? basePath + '/' : '') + 'websockify');
    }
    if (!url.searchParams.has('resize')) url.searchParams.set('resize', 'scale');
    if (!url.searchParams.has('autoconnect')) url.searchParams.set('autoconnect', '1');
    return url.toString();
  }

  root.buildBrowserViewerUrl = buildBrowserViewerUrl;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { buildBrowserViewerUrl: buildBrowserViewerUrl };
  }
})(typeof window !== 'undefined' ? window : globalThis);
