# Low-Level Design (LLD)
**Project:** CollabEdit  
**Version:** 1.0  
**Date:** 2026-11-22

---

## 1. Module Map

```
doc_editor/
  settings/base.py          ← shared settings
  settings/development.py   ← DEBUG=True, SQLite fallback option
  settings/production.py    ← HTTPS, HSTS, ALLOWED_HOSTS, secure cookies
  settings/__init__.py      ← selects settings module from DJANGO_SETTINGS_MODULE
  asgi.py                   ← ProtocolTypeRouter + AllowedHostsOriginValidator + AuthMiddlewareStack
  urls.py                   ← includes accounts/, documents/, health/

apps/accounts/
  models.py                 ← User(AbstractUser) — no extra fields in V1
  views.py                  ← RegisterView, LoginView (CBV wrapping Django auth)
  forms.py                  ← RegistrationForm, LoginForm
  urls.py                   ← /accounts/ prefix
  services.py               ← create_user(username, email, password)
  tests/
    test_views.py
    test_forms.py
    test_services.py

apps/documents/
  models.py                 ← Document (extended), DocumentPermission, DocumentRevision
  views.py                  ← DocumentListView, DocumentDetailView, DocumentCreateView,
                                PermissionCreateView, PermissionUpdateView, PermissionDeleteView,
                                RevisionListView, RevisionRestoreView
  forms.py                  ← DocumentCreateForm, ShareDocumentForm
  urls.py                   ← /documents/ prefix
  services.py               ← create_document, share_document, revoke_permission,
                                create_revision, restore_revision
  selectors.py              ← get_document_for_user, list_user_documents, get_revisions
  permissions.py            ← get_user_role, has_view_permission, has_edit_permission
  admin.py                  ← Document, DocumentPermission, DocumentRevision registered
  tests/
    test_models.py
    test_views.py
    test_services.py
    test_permissions.py

apps/collaboration/
  consumers.py              ← DocumentConsumer(AsyncWebsocketConsumer)
  routing.py                ← websocket_urlpatterns
  middleware.py             ← (additional WS middleware if needed)
  presence.py               ← PresenceManager (Redis hash + sorted set)
  persistence.py            ← flush_to_db(doc_id, ydoc)
  tests/
    test_consumers.py
    test_presence.py
    test_persistence.py

apps/audit/
  models.py                 ← AuditEvent
  services.py               ← log_event(event_type, actor, document, ...)
  tests/
    test_audit.py

core/
  exceptions.py             ← PermissionDenied, DocumentNotFound, RateLimitExceeded
  logging.py                ← JSON logging configuration dict
  middleware.py             ← RequestIdMiddleware, TokenBucketRateLimitMiddleware, SecurityHeadersMiddleware
  rate_limiting.py          ← TokenBucket class + Lua script
  health_checks.py          ← /health/ view
```

---

## 2. `apps/collaboration/consumers.py` — Detailed Design

```python
class DocumentConsumer(AsyncWebsocketConsumer):
    """
    Async WebSocket consumer for real-time document collaboration.
    
    Protocol: y-websocket binary protocol over WebSocket.
    Message types (first byte):
        0 = Sync Step 1 (state vector)
        1 = Sync Step 2 (update for missing ops)
        2 = Yjs Update (apply delta)
        3 = Awareness Update (cursor/presence)
    
    Auth: Resolved by AuthMiddlewareStack before connect().
    Authorization: Checked in connect() before accept().
    """
    
    # Class-level: shared Yjs documents per room
    # {doc_id: Y.Doc} — in-process cache; one per ASGI worker
    _ydocs: dict[int, Y.Doc] = {}
    _flush_tasks: dict[int, asyncio.Task] = {}
    
    FLUSH_INTERVAL = 30         # seconds
    MAX_PAYLOAD = 1_048_576     # 1 MB
    WS_RATE_CAPACITY = 60       # tokens
    WS_RATE_REFILL = 20         # tokens/second
    
    async def connect(self):
        # 1. Authentication
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=4001)
            return
        
        # 2. Extract document ID from URL
        self.doc_uuid = self.scope["url_route"]["kwargs"]["doc_uuid"]
        
        # 3. Load document and check permission (async ORM)
        try:
            self.document = await Document.objects.select_related('owner').aget(
                group__name=self.doc_uuid, is_deleted=False
            )
        except Document.DoesNotExist:
            await self.close(code=4004)
            return
        
        self.role = await database_sync_to_async(get_user_role)(user, self.document)
        if self.role is None:
            await self.close(code=4003)
            return
        
        # 4. Accept connection
        await self.accept()
        
        self.user = user
        self.doc_id = self.document.id
        self.conn_id = str(uuid.uuid4())
        self.room_name = str(self.doc_uuid)
        self._update_count = 0
        
        # 5. Join channel group
        await self.channel_layer.group_add(self.room_name, self.channel_name)
        
        # 6. Add to presence
        await presence_manager.add_connection(self.doc_id, self.conn_id, user)
        
        # 7. Load or create Yjs doc
        ydoc = await self._get_or_load_ydoc()
        
        # 8. Send sync (state vector → client responds with missing ops)
        sync_msg = self._encode_sync_step1(ydoc)
        await self.send(bytes_data=sync_msg)
        
        # 9. Broadcast updated presence
        await self._broadcast_presence()
        
        # 10. Initialise rate limiter for this connection
        self._ws_limiter = TokenBucket(
            redis_client, self.WS_RATE_CAPACITY, self.WS_RATE_REFILL, 'ws'
        )
    
    async def receive_bytes(self, data: bytes):
        # 1. Payload size
        if len(data) > self.MAX_PAYLOAD:
            await self.close(code=4008)
            return
        
        # 2. Rate limit
        allowed, _ = await self._ws_limiter.is_allowed_async(self.conn_id)
        if not allowed:
            await self.close(code=4029)
            return
        
        # 3. Decode message type
        msg_type = data[0]
        
        if msg_type == 0:  # Sync Step 1
            await self._handle_sync_step1(data)
        elif msg_type == 2:  # Update
            if self.role == 'viewer':
                await self.close(code=4003)
                return
            await self._handle_update(data)
        elif msg_type == 3:  # Awareness
            await self._handle_awareness(data)
    
    async def _handle_update(self, data: bytes):
        update = data[1:]  # strip type byte
        ydoc = self._ydocs.get(self.doc_id)
        if ydoc:
            ydoc.apply_update(update)
        
        # Cache in Redis
        await self._cache_ydoc_state()
        
        # Broadcast to room (excluding sender via sender_channel_name)
        await self.channel_layer.group_send(self.room_name, {
            'type': 'yjs_update',
            'update': update,
            'sender': self.channel_name,
        })
        
        # Schedule flush
        await self._schedule_flush()
        
        # Auto-snapshot every 100 updates
        self._update_count += 1
        if self._update_count % 100 == 0:
            await self._create_auto_snapshot()
    
    async def yjs_update(self, event):
        """Receives a group_send broadcast; forwards to WebSocket (excluding sender)."""
        if event['sender'] == self.channel_name:
            return
        await self.send(bytes_data=bytes([2]) + event['update'])
    
    async def disconnect(self, close_code):
        if not hasattr(self, 'doc_id'):
            return  # connect() failed before setup; nothing to clean up
        
        # Cancel debounce timer
        task = self._flush_tasks.get(self.doc_id)
        if task:
            task.cancel()
        
        # Remove from presence
        remaining = await presence_manager.remove_connection(self.doc_id, self.conn_id)
        
        # Flush to DB if last connection
        if remaining == 0:
            ydoc = self._ydocs.get(self.doc_id)
            if ydoc:
                await persistence.flush_to_db(self.doc_id, ydoc)
                del self._ydocs[self.doc_id]
        
        await self._broadcast_presence()
        await self.channel_layer.group_discard(self.room_name, self.channel_name)
```

---

## 3. `apps/collaboration/presence.py` — Detailed Design

```python
class PresenceManager:
    """
    Connection-aware presence tracking using Redis.
    
    Data structures:
        ZADD collabedit:presence:{doc_id} {timestamp} {conn_id}
            → Sorted set for efficient cleanup of stale connections
        HSET collabedit:presence_data:{doc_id}:{conn_id}
            {user_id, username, color, connected_at}
            EXPIRE 30s  → Stale entry cleanup fallback
    """
    
    async def add_connection(self, doc_id: int, conn_id: str, user) -> int:
        now = time.time()
        async with redis_client.pipeline() as pipe:
            pipe.zadd(f"collabedit:presence:{doc_id}", {conn_id: now})
            pipe.hset(
                f"collabedit:presence_data:{doc_id}:{conn_id}",
                mapping={
                    'user_id': user.id,
                    'username': user.username,
                    'color': self._user_color(user.id),
                    'connected_at': now,
                }
            )
            pipe.expire(f"collabedit:presence_data:{doc_id}:{conn_id}", 30)
            results = await pipe.execute()
        count = await redis_client.zcard(f"collabedit:presence:{doc_id}")
        return count
    
    async def remove_connection(self, doc_id: int, conn_id: str) -> int:
        async with redis_client.pipeline() as pipe:
            pipe.zrem(f"collabedit:presence:{doc_id}", conn_id)
            pipe.delete(f"collabedit:presence_data:{doc_id}:{conn_id}")
            await pipe.execute()
        return await redis_client.zcard(f"collabedit:presence:{doc_id}")
    
    async def get_active_users(self, doc_id: int) -> list[dict]:
        conn_ids = await redis_client.zrange(f"collabedit:presence:{doc_id}", 0, -1)
        users = []
        for conn_id in conn_ids:
            data = await redis_client.hgetall(f"collabedit:presence_data:{doc_id}:{conn_id}")
            if data:
                users.append(data)
        # Deduplicate by user_id (multiple tabs)
        seen = set()
        unique = []
        for u in users:
            if u['user_id'] not in seen:
                seen.add(u['user_id'])
                unique.append(u)
        return unique
    
    def _user_color(self, user_id: int) -> str:
        """Deterministic color from user_id for cursor display."""
        COLORS = ['#f472b6', '#22d3ee', '#c084fc', '#fb923c', '#34d399', '#60a5fa']
        return COLORS[user_id % len(COLORS)]
```

---

## 4. `apps/collaboration/persistence.py` — Detailed Design

```python
async def flush_to_db(doc_id: int, ydoc) -> bool:
    """
    Flush the current Yjs document state to PostgreSQL.
    
    Uses select_for_update() to prevent concurrent flush races.
    Retries up to 3 times on OperationalError.
    Returns True if flush succeeded, False if all retries failed.
    """
    encoded_state = ydoc.encode_state()
    
    for attempt in range(3):
        try:
            async with transaction.atomic():
                doc = await Document.objects.select_for_update().aget(id=doc_id)
                doc.yjs_state = encoded_state
                doc.updated_at = timezone.now()
                await doc.asave(update_fields=['yjs_state', 'updated_at'])
            
            # Update Redis TTL on success
            await redis_client.set(
                f"collabedit:ydoc:{doc_id}",
                encoded_state,
                ex=86400  # 24 hours
            )
            logger.info("flush_to_db succeeded", extra={"doc_id": doc_id, "attempt": attempt + 1})
            return True
        
        except OperationalError as e:
            backoff = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(
                "flush_to_db failed, retrying",
                extra={"doc_id": doc_id, "attempt": attempt + 1, "error": str(e), "backoff": backoff}
            )
            if attempt < 2:
                await asyncio.sleep(backoff)
    
    logger.error("flush_to_db failed after 3 attempts", extra={"doc_id": doc_id})
    return False
```

---

## 5. `core/rate_limiting.py` — Detailed Design

```python
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

local elapsed = math.max(0, now - last_refill)
local refilled = math.min(capacity, tokens + elapsed * refill_rate)

if refilled >= cost then
    redis.call('HMSET', key, 'tokens', refilled - cost, 'last_refill', now)
    redis.call('EXPIRE', key, 60)
    return {1, 0}
else
    local retry_after = (cost - refilled) / refill_rate
    redis.call('HMSET', key, 'tokens', refilled, 'last_refill', now)
    redis.call('EXPIRE', key, 60)
    return {0, retry_after * 1000}  -- retry_after in milliseconds
end
"""

class TokenBucket:
    def __init__(self, redis_client, capacity: float, refill_rate: float, key_prefix: str):
        self._redis = redis_client
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._key_prefix = key_prefix
        self._script = redis_client.register_script(TOKEN_BUCKET_LUA)
    
    def is_allowed(self, identifier: str, cost: float = 1.0) -> tuple[bool, float]:
        key = f"collabedit:rl:{self._key_prefix}:{identifier}"
        try:
            result = self._script(keys=[key], args=[self._capacity, self._refill_rate, time.time(), cost])
            allowed = bool(result[0])
            retry_after = result[1] / 1000.0  # convert ms to seconds
            return allowed, retry_after
        except redis.ConnectionError:
            logger.warning("Rate limit check failed: Redis unavailable — allowing request")
            return True, 0.0
    
    async def is_allowed_async(self, identifier: str, cost: float = 1.0) -> tuple[bool, float]:
        return await asyncio.get_event_loop().run_in_executor(
            None, self.is_allowed, identifier, cost
        )
```

---

## 6. `core/health_checks.py` — Detailed Design

```python
async def health_check(request):
    """
    GET /health/
    Returns 200 if all services are operational, 503 if any are degraded.
    No authentication required.
    """
    checks = {}
    
    # PostgreSQL check
    try:
        await database_sync_to_async(connection.ensure_connection)()
        checks['db'] = 'ok'
    except Exception as e:
        logger.error("Health check: DB failed", extra={"error": str(e)})
        checks['db'] = 'error'
    
    # Redis check
    try:
        await redis_client.ping()
        checks['redis'] = 'ok'
    except Exception as e:
        logger.error("Health check: Redis failed", extra={"error": str(e)})
        checks['redis'] = 'error'
    
    all_ok = all(v == 'ok' for v in checks.values())
    checks['status'] = 'ok' if all_ok else 'degraded'
    
    return JsonResponse(checks, status=200 if all_ok else 503)
```

---

## 7. Settings Architecture

```
doc_editor/settings/
  __init__.py     → reads DJANGO_SETTINGS_MODULE; validates required env vars
  base.py         → all shared settings (apps, middleware, templates, auth, channels, etc.)
  development.py  → DEBUG=True, relaxed ALLOWED_HOSTS, console logging
  production.py   → ALLOWED_HOSTS=[env], HTTPS, HSTS, secure cookies, JSON logging
```

**Environment variable validation (base.py):**
```python
import sys

_REQUIRED_ENV_VARS = ['SECRET_KEY', 'DATABASE_URL', 'REDIS_URL']
_missing = [v for v in _REQUIRED_ENV_VARS if not os.getenv(v)]
if _missing:
    print(f"ERROR: Missing required environment variables: {', '.join(_missing)}", file=sys.stderr)
    sys.exit(1)
```

This runs at startup and exits cleanly with a descriptive error rather than a confusing `None` key error later.

---

## 8. URL Structure

```
/                               → home view (landing page)
/home                           → index view (creates new document, redirects)
/<uuid>/                        → room view (redirects to /documents/<uuid>/) [backward compat]
/documents/                     → DocumentListView
/documents/create/              → DocumentCreateView  
/documents/<uuid>/              → DocumentDetailView (editor)
/documents/<uuid>/permissions/  → PermissionCreateView (POST)
/documents/<uuid>/permissions/<user_id>/  → PermissionUpdateView (PATCH), PermissionDeleteView (DELETE)
/documents/<uuid>/revisions/    → RevisionListView (GET), RevisionCreateView (POST)
/documents/<uuid>/revisions/<id>/restore/  → RevisionRestoreView (POST)
/accounts/register/             → RegisterView
/accounts/login/                → LoginView
/accounts/logout/               → LogoutView (POST)
/health/                        → health_check
/admin/                         → Django admin
/ws/documents/<uuid>/           → DocumentConsumer (WebSocket)
```
