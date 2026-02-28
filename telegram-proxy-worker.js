/**
 * GhostDesk — Cloudflare Worker: Telegram API Proxy
 *
 * Deploy this Worker to bypass regional Telegram API blocks.
 * All requests to your Worker URL are forwarded to api.telegram.org.
 *
 * Deploy in 60 seconds:
 *   1. Go to https://workers.cloudflare.com  (free account)
 *   2. Create Worker → paste this file → Save & Deploy
 *   3. Copy your Worker URL, e.g. https://ghostdesk-proxy.yourname.workers.dev
 *   4. Add to ~/.ghostdesk/.env:
 *        TELEGRAM_API_BASE=https://ghostdesk-proxy.yourname.workers.dev
 *   5. Run ghostdesk — no VPN needed.
 *
 * Security: the Worker only forwards to api.telegram.org, nothing else.
 * Your bot token travels inside the URL path (same as normal Telegram API).
 */

export default {
  async fetch(request) {
    const url = new URL(request.url);

    // Rewrite host to the real Telegram Bot API
    url.hostname = "api.telegram.org";
    url.protocol = "https:";
    url.port = "";

    const proxied = new Request(url.toString(), {
      method:  request.method,
      headers: request.headers,
      body:    request.body,
    });

    return fetch(proxied);
  },
};
