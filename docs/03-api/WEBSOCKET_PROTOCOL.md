# WebSocket Protocol Reference

## CollabEdit WebSocket Collaboration Protocol

**Version:** 1.0  
**WebSocket URL:** `wss://<host>/ws/documents/<uuid>/`  
**Message format:** Binary frames (all messages except JSON text pushes from server)  
**Sub-protocol:** Adapted y-websocket binary protocol

---

## 1. Connection handshake

### 1.1 Client initiates connection
```
Client → GET /ws/documents/<uuid>/
         Upgrade: websocket
         Cookie: sessionid=<session-cookie>
         Origin: https://<host>
```

### 1.2 Server validates
1. `AllowedHostsOriginValidator` — rejects cross-origin requests (closes without upgrade)
2. `AuthMiddlewareStack` — resolves session cookie to `scope["user"]`
3. `DocumentConsumer.connect()`:
   - If unauthenticated → close `4001`
   - If document not found → close `4004`
   - If no permission → close `4003`
   - Otherwise → `101 Switching Protocols`

### 1.3 Server sends initial sync (Sync Step 2)
Immediately after accepting, the server sends the full Yjs state:
```
Server → Binary frame: [0x01] [<encoded-yjs-state>]
         (MSG_SYNC_STEP2 = 0x01, payload = full state vector)
```

---

## 2. Message types

| Byte | Name | Direction | Description |
|---|---|---|---|
| `0x00` | `MSG_SYNC_STEP1` | Client → Server | Client sends its state vector; server responds with missing updates |
| `0x01` | `MSG_SYNC_STEP2` | Server → Client | Server sends full or delta state to sync the client |
| `0x02` | `MSG_UPDATE` | Bidirectional | Yjs document delta (editor-only send; server broadcasts) |
| `0x03` | `MSG_AWARENESS` | Bidirectional | Cursor/selection awareness state (all roles can send) |

> **Text frames:** The server also sends JSON text frames for presence updates (see §4). Clients must handle both binary and text frames.

---

## 3. Message format

### 3.1 MSG_SYNC_STEP1 (0x00)
```
Byte 0:   0x00
Bytes 1…: state_vector (Yjs encoded state vector of client's Y.Doc)
```
Client sends this when it wants to sync. Server responds with MSG_SYNC_STEP2 containing any updates the client is missing.

### 3.2 MSG_SYNC_STEP2 (0x01)
```
Byte 0:   0x01
Bytes 1…: encoded_state (Yjs Y.applyUpdate compatible bytes)
```
Server sends this either:
- Immediately on connect (full state), or
- In response to a MSG_SYNC_STEP1 (delta of missing updates)

Client applies via `Y.applyUpdate(ydoc, payload)`.

### 3.3 MSG_UPDATE (0x02)
```
Byte 0:   0x02
Bytes 1…: yjs_update (Y.encodeStateAsUpdate output)
```
- **Client → Server:** Editor sends a Yjs delta after local changes
- **Server → Client:** Broadcast of another user's delta (server strips sender from broadcast)

Client applies via `Y.applyUpdate(ydoc, payload)`.

### 3.4 MSG_AWARENESS (0x03)
```
Byte 0:   0x03
Bytes 1…: awareness_payload (Yjs awareness protocol encoding)
```
Cursor/selection/user metadata. Broadcast to all other connections in the same document room.

---

## 4. Server-push text frames (presence)

The server pushes a JSON text frame whenever the connected user count for a document changes (someone connects or disconnects):

```json
{
  "type": "presence",
  "users": [
    { "username": "alice", "user_id": 1 },
    { "username": "bob",   "user_id": 2 }
  ]
}
```

Clients should update the presence panel UI on receipt of this message.

---

## 5. Close codes

| Code | Name | Trigger |
|---|---|---|
| `4001` | Unauthenticated | WebSocket connection with no valid session |
| `4003` | Unauthorized | No permission to view this document; or viewer sent MSG_UPDATE |
| `4004` | Not found | Document UUID does not exist or is deleted |
| `4008` | Payload too large | Message exceeded 1 MB |
| `4029` | Rate limited | WebSocket Token Bucket exhausted (60 tokens, 20/s refill) |

---

## 6. Rate limiting

Each WebSocket connection has an independent Token Bucket in Redis:
- **Key:** `collabedit:rl:ws:{conn_id}`
- **Capacity:** 60 tokens (burst)
- **Refill rate:** 20 tokens/second
- **Cost per message:** 1 token
- **Exceeded:** Server closes with code `4029`

---

## 7. Reconnection

Clients must implement exponential backoff reconnection:

```
attempt 1: wait 1 s
attempt 2: wait 2 s
attempt 3: wait 4 s
...
max delay: 30 s
```

On reconnect, the client sends MSG_SYNC_STEP1 with its current state vector; the server responds with any missing updates. Because Yjs is a CRDT, edits made offline are automatically merged when the client reconnects.

---

## 8. Permissions

| Role | MSG_SYNC_STEP1 | MSG_UPDATE | MSG_AWARENESS |
|---|---|---|---|
| owner | ✅ | ✅ | ✅ |
| editor | ✅ | ✅ | ✅ |
| viewer | ✅ | ❌ close 4003 | ✅ |

---

## 9. Example client flow

```javascript
// 1. Connect
const ws = new WebSocket("wss://host/ws/documents/<uuid>/");
ws.binaryType = "arraybuffer";

// 2. On open — send Sync Step 1
ws.addEventListener("open", () => {
  const sv = Y.encodeStateVector(ydoc);
  const msg = new Uint8Array(1 + sv.length);
  msg[0] = 0x00;  // MSG_SYNC_STEP1
  msg.set(sv, 1);
  ws.send(msg);
});

// 3. On message — apply updates
ws.addEventListener("message", (evt) => {
  if (typeof evt.data === "string") {
    // JSON text frame (presence)
    const data = JSON.parse(evt.data);
    if (data.type === "presence") updateUI(data.users);
    return;
  }
  const data = new Uint8Array(evt.data);
  const type = data[0];
  const payload = data.slice(1);
  if (type === 0x01 || type === 0x02) {   // SYNC2 or UPDATE
    Y.applyUpdate(ydoc, payload);
  }
});

// 4. On local Y.Doc change — send update
ydoc.on("update", (update, origin) => {
  const msg = new Uint8Array(1 + update.length);
  msg[0] = 0x02;  // MSG_UPDATE
  msg.set(update, 1);
  ws.send(msg);
});
```
