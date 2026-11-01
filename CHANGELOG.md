# Changelog

## 0.1.0

- Live HTML over Hibira: `broadcast_append`, `_prepend`, `_replace`,
  `_update`, `_before`, `_after`, `_remove` and `_refresh` send template
  fragments to every page with `{% hibira_stream %}`. No Django Channels, ASGI
  server or Redis needed.
- `@broadcasts` model decorator: creates append, updates replace, deletes
  remove (or `refresh=True` for page refreshes).
- Broadcasts wait for the transaction to commit; delivery errors are logged.
- Fragments over the plan's message size limit become a page refresh
  (`HIBIRA["OVERSIZE"]`).
- Channel auth for your own private and presence channels
  (`HIBIRA["AUTHORIZE_CHANNEL"]`, `POST /hibira/auth`).
- Verified webhooks, including the previous secret during rotation
  (`on_webhook`, `webhook_received`, `POST /hibira/webhooks`).
- Push user tokens (`GET /hibira/push/token`).
- `{% hibira_scripts %}`, `{% hibira_stream %}`, `{% dom_id %}`; browser script
  with htmx and Turbo 8 support, pusher-js 8.6.0 bundled.
- `manage.py hibira_check`, system checks, `django_hibira.testing.capture_broadcasts`.
