FROM kasmweb/chromium:1.17.0

USER root

RUN mkdir -p /opt/agent-browser /home/kasm-user/.config/chromium \
    && chown -R 1000:1000 /home/kasm-user/.config \
    && if [ -x /usr/bin/chromium ] && [ ! -e /usr/bin/chromium-orig ]; then \
        cp -a /usr/bin/chromium /usr/bin/chromium-orig; \
    fi \
    && test -x /usr/bin/chromium-orig

COPY --chmod=0755 chromium-browser /usr/bin/chromium
COPY --chmod=0755 cdp-proxy.py /opt/agent-browser/cdp-proxy.py

RUN sed -i 's/ -sslOnly / ${KASMVNC_SSL_ONLY--sslOnly} /g' /dockerstartup/vnc_startup.sh
RUN sed -i 's/require_ssl: true/require_ssl: false/g' /usr/share/kasmvnc/kasmvnc_defaults.yaml
RUN find /usr/share/kasmvnc/www -maxdepth 1 -name '*.html' -exec \
    sed -i 's/isInsideKasmVDI=window.self!==window.top/isInsideKasmVDI=false/g; s/isInsideKasmVDI=!0/isInsideKasmVDI=false/g' {} \;
RUN sed -i 's/const s=(Date.now()-a\.rfb\.lastActiveAt)\/1e3;/if(!a.rfb)return;const s=(Date.now()-(a.rfb.lastActiveAt||Date.now()))\/1e3;/g' \
    /usr/share/kasmvnc/www/main.bundle.js

EXPOSE 6901 9223

HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9223/json/version', timeout=2)"

USER 1000
