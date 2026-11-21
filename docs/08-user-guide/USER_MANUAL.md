# User Manual

## CollabEdit — Getting Started Guide

**Version:** 2.0  
**Audience:** End users

---

## 1. What is CollabEdit?

CollabEdit is a real-time collaborative document editor. Multiple people can type in the same document at the same time, and everyone sees each other's changes instantly — no refreshing required.

---

## 2. Creating an account

1. Go to the CollabEdit homepage
2. Click **Sign up** in the top-right corner
3. Enter a username (required), email address (optional), and a password
4. Click **Create account** — you'll be logged in automatically

---

## 3. Creating a document

1. After logging in, you'll see your document list
2. Click **+ New document** (top-right)
3. A new untitled document opens immediately in the editor
4. Click on "Untitled document" at the top to rename it — changes save automatically

---

## 4. Editing a document

- The editor supports **rich text**: bold, italic, underline, headings, lists, code blocks, and links
- Use the toolbar at the top of the editor
- Changes are saved automatically — look for the "Saved" indicator in the top bar

**Keyboard shortcuts:**

| Shortcut | Action |
|---|---|
| `Ctrl+B` | Bold |
| `Ctrl+I` | Italic |
| `Ctrl+U` | Underline |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |

---

## 5. Collaborating in real time

- Share the document URL with colleagues (or use the **Share** panel)
- Everyone who has access sees each other's edits as they type
- The **Online now** panel (right sidebar) shows who is currently editing
- If your connection drops, edits you made offline will sync when you reconnect

---

## 6. Sharing a document

1. Open the document you want to share
2. In the right sidebar, find the **Share document** panel (visible to owners only)
3. Enter the **username** of the person you want to share with
4. Choose their role:
   - **Editor** — can read and write
   - **Viewer** — can only read; cannot type
5. Click **Share**

The person will now see the document in their own document list under "Shared with you".

---

## 7. Managing permissions

As the **owner**, you can see all shared users at the bottom of the Share panel.

To **revoke access**:
1. Find the user in the "Shared with" list
2. Click the ✕ button next to their name
3. They lose access immediately (open sessions are closed on next action)

---

## 8. Revision history

CollabEdit automatically saves snapshots of your document every 100 edits.

To view or restore a revision:
1. Click **Revisions** in the editor top bar
2. You'll see a list of all saved revisions with dates and who created them
3. Click **Restore** to roll back to that version
   - The current state is automatically saved as a "pre-restore" snapshot first
   - You can always undo a restore by restoring the pre-restore snapshot

To **manually save a snapshot**:
- On the revisions page, click **Save revision now**

---

## 9. Document list

Your homepage (`/documents/`) shows:
- **Owned by you** — documents you created
- **Shared with you** — documents others have shared with you, showing your role (Editor / Viewer)

Each card shows the document title, when it was last updated, and your role.

---

## 10. Deleting a document

1. Open the document
2. *(Currently only available via the editor — full delete UI coming in V2)*

> **Note:** Deleted documents are soft-deleted (not permanently removed). They can be recovered by an admin if needed.

---

## 11. Roles explained

| Role | Can view | Can edit | Can share | Can delete | Can restore revisions |
|---|---|---|---|---|---|
| **Owner** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Editor** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Viewer** | ✅ | ❌ | ❌ | ❌ | ❌ |

---

## 12. Troubleshooting

### "Disconnected — reconnecting…"
Your internet connection dropped. The editor reconnects automatically — any edits you made will sync once you're back online.

### "Access denied" (error page)
You don't have permission to view this document. Ask the owner to share it with you.

### "Not authenticated" / Redirected to login
Your session expired. Log in again and return to the document.

### Changes aren't saving
Check the save status indicator in the top bar. If it shows "Connection error", there may be a temporary server issue. Wait a moment and try again.

### I can't type (read-only)
You have **Viewer** access. Ask the owner to upgrade your role to **Editor**.

---

## 13. Privacy and data

- Your documents are private by default — only you can see them until you share them
- Sharing a document with a user does not share your other documents
- Document content is stored encrypted in transit (HTTPS/WSS)
- Revision history is kept for all documents

---

## 14. Getting help

Contact your system administrator, or file an issue at the project repository.
