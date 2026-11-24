# 📝 Real-Time Collaborative Editor

A real-time collaborative document editor where multiple users can write and edit documents simultaneously. Changes sync instantly across all connected clients via WebSockets.

**🔗 Live Demo:** [realtimedocs.onrender.com](https://realtimedocs.onrender.com)

---

## ✨ Features

- ⚡ **Real-time sync** — every keystroke is broadcast to all connected users instantly
- 🔗 **UUID-based room URLs** — each document gets a unique shareable link
- 👥 **Online presence counter** — shows how many users are in the room
- 🚀 **Redis caching** — document content served from cache, not DB, on every load
- 🔓 **No sign-in required** — open a link and start writing
- 💾 **Auto-saved** — content persists in PostgreSQL
- ✍️ **Rich text editor** — bold, italic, underline, headings, lists via Quill.js

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 5, Django Channels |
| WebSockets | ASGI, Uvicorn |
| Cache / Pub-Sub | Redis |
| Database | PostgreSQL (NeonDB) |
| Editor | Quill.js |
| Containerization | Docker, Docker Compose |
| Deployment | Render |

---

## 📁 Project Structure

```
Real-Time-Collaborative-Editor/
├── doc_editor/
│   ├── asgi.py          # ASGI config with WebSocket routing
│   ├── settings.py      # Project settings
│   └── urls.py          # Root URL routing
├── documents/
│   ├── consumers.py     # WebSocket consumer (Django Channels)
│   ├── models.py        # Group, Document models
│   ├── views.py         # home, index, room views
│   ├── urls.py          # URL routing
│   └── templates/
│       └── documents/
│           ├── home.html    # Landing page
│           └── index.html   # Editor page
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## 🔄 How It Works

```
User visits /          → Landing page (home.html)
Clicks "Create"        → /home → UUID generated → redirect to /uuid/
User visits /uuid/     → Editor loads, WebSocket connects
User types             → WebSocket sends HTML to server
Server broadcasts      → All connected clients receive and render update
Content saved          → Redis cache + PostgreSQL on each change
```

### WebSocket Flow

```
Client connects → ws://host/ws/editor/<room_id>/
                → Consumer joins channel group

Client types    → socket.send(HTML)
                → Consumer receives
                → Broadcasts to group
                → Saves to Redis + DB

New client joins → Receives latest content from Redis cache
```

### Architecture

```
Browser (User A)          Browser (User B)
     │                         │
     │  WebSocket              │  WebSocket
     └──────────┬──────────────┘
                │
         [Django Channels]
         [Uvicorn ASGI Server]
                │
         DocumentConsumer
                │
        ┌───────┴────────┐
        │                │
    [Redis]          [PostgreSQL]
  (Channel Layer     (Persistent
   + Cache)           Storage)
```

---

## 🚀 Local Setup

### Prerequisites
- Docker Desktop installed and running

### Run locally

```bash
# Clone the repo
git clone https://github.com/k4rtikx/Real-Time-Collaborative-Editor.git
cd Real-Time-Collaborative-Editor

# Start all services (Django + Redis)
docker-compose up --build
```

Visit `http://localhost:8000`

> ⚠️ **Always use `docker-compose up`**, not `uvicorn` directly.  
> Running `uvicorn` alone won't start Redis, and the app will crash.

---

## ⚙️ Environment Variables

Create a `.env` file in the root:

```env
DATABASE_URL=your_postgresql_connection_string
REDIS_URL=redis://redis:6379
SECRET_KEY=your_django_secret_key
DEBUG=False
```

---

## 🌐 API / URL Routes

| URL | View | Description |
|---|---|---|
| `/` | `home` | Landing page |
| `/home` | `index` | Generates UUID, redirects to editor |
| `/<uuid>/` | `room` | Opens the collaborative editor |
| `/ws/editor/<uuid>/` | WebSocket | Real-time sync channel |

---

## ☁️ Deployment (Render)

This project is deployed on Render using Docker.

- Django + Uvicorn runs as a **Web Service**
- Redis runs as a separate **Redis service** on Render
- PostgreSQL hosted on **NeonDB**
- `REDIS_URL` and `DATABASE_URL` set as environment variables in Render dashboard

---

## 👨‍💻 Author

**Kartik Singh**  
B.Tech Information Technology — Alliance College of Engineering and Design, Bengaluru  
GitHub: [github.com/k4rtikx](https://github.com/k4rtikx)  
LinkedIn: [linkedin.com/in/kartik-singh-3b061b320](https://linkedin.com/in/kartik-singh-3b061b320)
