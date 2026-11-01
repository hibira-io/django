# django-hibira example: live chat room

A WSGI Django project with live messages (`@broadcasts` on `Message`), a live
message counter (`broadcast_update`) and a "here now" list on a presence
channel. Messages are sent with htmx.

```sh
pip install -e ..
export HIBIRA_APP_ID=... HIBIRA_APP_KEY=... HIBIRA_APP_SECRET=...
python manage.py migrate
python manage.py runserver
```

Add `http://localhost:8000` (or `http://127.0.0.1:8000`) to the app's allowed
origins, then open http://localhost:8000 in two browsers.

## 中文摘要

這是一個用 django-hibira 做的即時聊天室範例：訊息即時出現、訊息數即時更新、右側顯示目前在線的人（presence 頻道）。設定三個 `HIBIRA_*` 環境變數並把 `http://localhost:8000` 加入 app 的允許來源後，`migrate`、`runserver`，用兩個瀏覽器打開即可。
