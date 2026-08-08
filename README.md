# Orbit · To-Do

Zero-dependency to-do app. Python stdlib backend (`http.server` + `sqlite3`),
vanilla HTML/CSS/JS frontend. No pip install, no npm, no build step.

## Run

```
python main.py         # opens http://127.0.0.1:8000/
```

One process serves both the API and the UI. (`cd Backend && python app.py`
still works if you prefer starting it from there.)

## Features

- Add, rename (click the text), complete, delete
- **Undo** — deleting shows an Undo button for a few seconds
- **Priority** (colour rail) and **due dates**, overdue shown in red
- **Recurring tasks** — daily / weekly / monthly; ticking one off creates the
  next occurrence. Monthly clamps, so 31 Jan repeats to 28 Feb.
- **Tags** — type `#home` anywhere in a task; tag chips appear and filter
- **Search** and All / Active / Done filters
- **Drag to reorder** (only while unfiltered, so the order you see is the real one)
- **Keyboard**: `n` new · `/` search · `j`/`k` move · `x` done · `e` rename ·
  `Del` delete · `Esc` leave a field
- **Reminders** — browser notification for anything overdue or due today
- **Email nudge** — a daily mail about missed work, for when the app is closed

## Layout

```
main.py        start here
Backend/
  app.py       HTTP routes, static files, Basic auth
  db.py        SQLite storage, validation, recurrence
  mailer.py    daily overdue email
  todo.db      created on first run
Frontend/
  index.html   markup
  style.css    aurora background + glass panel
  app.js       fetch calls, render, events, reminders
```

## Reminders

Click 🔔 to allow notifications. Anything overdue or due today nudges you once
per day, and the tab re-checks every minute. This only works while the app is
open in a tab (background tabs count) — for missed work when it is closed,
turn on the email nudge below.

## Email nudge (optional)

Off unless configured. Gmail needs an [App Password](https://myaccount.google.com/apppasswords),
not your normal login.

```
set TODO_SMTP_HOST=smtp.gmail.com
set TODO_SMTP_PORT=587
set TODO_SMTP_USER=you@gmail.com
set TODO_SMTP_PASS=your-app-password
set TODO_EMAIL_TO=you@gmail.com
set TODO_EMAIL_HOUR=8
python main.py
```

One mail a day, listing everything overdue. Port 465 switches to SSL
automatically. If the mail server is unreachable the app keeps running and
prints `[mail] skipped: ...`.

## Phone access (same wifi)

```
set TODO_HOST=0.0.0.0
set TODO_PASSWORD=something
python main.py                 # prints the address to open on your phone
```

The password is Basic auth, sent in clear text over plain HTTP — fine for your
own wifi, not for the open internet.

To serve HTTPS instead, point `TODO_CERT` at a PEM certificate (and `TODO_KEY`
at the key, if it is a separate file). A self-signed one is enough on your own
network; browsers will warn once and let you continue.

```
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "//CN=localhost"
set TODO_CERT=cert.pem
set TODO_KEY=key.pem
```

## API

| Method | Path                | Body                              |
|--------|---------------------|-----------------------------------|
| GET    | `/api/tasks`        | –                                 |
| POST   | `/api/tasks`        | `{title, priority?, due?, repeat?}` |
| PATCH  | `/api/tasks/<id>`   | any of `title/priority/due/done/repeat` |
| PATCH  | `/api/tasks/order`  | `{ids: [...]}`                    |
| DELETE | `/api/tasks/<id>`   | –                                 |
| DELETE | `/api/tasks/done`   | – (clears completed)              |

## Environment variables

| Name | Default | What it does |
|------|---------|--------------|
| `TODO_HOST` | `127.0.0.1` | `0.0.0.0` to allow other devices |
| `TODO_PORT` | `8000` | port |
| `TODO_PASSWORD` | – | Basic auth password when set |
| `TODO_CERT` | – | PEM certificate; serves HTTPS when set |
| `TODO_KEY` | – | private key, if separate from the certificate |
| `TODO_DB` | `Backend/todo.db` | database file |
| `TODO_NO_BROWSER` | – | don't auto-open a browser |
