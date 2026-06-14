FROM kasmweb/chromium:1.17.0

USER root

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends wget ca-certificates \
    && wget -q -O /tmp/google-chrome.deb \
        https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y -qq /tmp/google-chrome.deb \
    && rm -f /tmp/google-chrome.deb \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/agent-browser /etc/opt/chrome/policies/managed \
    && printf '%s\n' '{"CommandLineFlagSecurityWarningsEnabled":false}' \
        > /etc/opt/chrome/policies/managed/virtual-office.json \
    && sed -i 's/^PGREP="chromium"/PGREP="chrome"/' \
        /dockerstartup/custom_startup.sh

COPY --chmod=0755 chromium-browser /usr/bin/chromium
COPY --chmod=0755 cdp-proxy.py /opt/agent-browser/cdp-proxy.py

EXPOSE 6901 9223

HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9223/json/version', timeout=2)"

USER 1000
