#!/bin/bash
set -e

# Fix kasm_viewer to have write permissions (not read-only).
sed -i 's/kasm_viewer:.*:r$/kasm_viewer:'"$(grep kasm_user /home/kasm-user/.kasmpasswd | cut -d: -f2)"':wo/' /home/kasm-user/.kasmpasswd

exec python3 /tmp/cdp-proxy.py
