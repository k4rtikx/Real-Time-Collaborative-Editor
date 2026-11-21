# User Stories
**Project:** CollabEdit  
**Version:** 1.0  
**Date:** 2026-11-22

---

## Epic 1 — Authentication

**US-001**  
*As a new visitor, I want to register with a username, email, and password so that I can access the platform.*  
Priority: P0 | Status: NOT STARTED

**US-002**  
*As a registered user, I want to log in with my credentials so that I can access my documents.*  
Priority: P0 | Status: NOT STARTED

**US-003**  
*As a logged-in user, I want to log out so that my session is terminated on shared devices.*  
Priority: P0 | Status: NOT STARTED

**US-004**  
*As a visitor, if I try to access a document URL without being logged in, I want to be redirected to the login page and then to my intended destination after login.*  
Priority: P0 | Status: NOT STARTED

---

## Epic 2 — Document Management

**US-005**  
*As an authenticated user, I want to create a new document so that I can start writing.*  
Priority: P0 | Status: NOT STARTED

**US-006**  
*As an authenticated user, I want to see a list of all documents I own or have access to so that I can navigate to them.*  
Priority: P0 | Status: NOT STARTED

**US-007**  
*As a document owner, I want to rename my document so that collaborators understand its purpose.*  
Priority: P1 | Status: NOT STARTED

**US-008**  
*As a document owner, I want to delete a document so that I can remove content I no longer need.*  
Priority: P1 | Status: NOT STARTED

**US-009**  
*As any user, if I try to access a document I have no permission to see, I want to receive a clear error message rather than a redirect loop or a 404.*  
Priority: P0 | Status: NOT STARTED

---

## Epic 3 — Sharing and Permissions

**US-010**  
*As a document owner, I want to share my document with another registered user by their username, granting them Editor or Viewer access, so that we can collaborate.*  
Priority: P0 | Status: NOT STARTED

**US-011**  
*As a document owner, I want to change a collaborator's role from Editor to Viewer (or vice versa) so that I can control who can make changes.*  
Priority: P1 | Status: NOT STARTED

**US-012**  
*As a document owner, I want to revoke a collaborator's access so that they can no longer view or edit the document.*  
Priority: P1 | Status: NOT STARTED

**US-013**  
*As a document owner, I want to see a list of everyone who has access to my document and what their roles are.*  
Priority: P1 | Status: NOT STARTED

---

## Epic 4 — Collaborative Editing

**US-014**  
*As an Editor, I want my keystrokes to appear instantly on the screens of all other connected users so that collaboration feels synchronous.*  
Priority: P0 | Status: NOT STARTED

**US-015**  
*As an Editor, I want edits from multiple users typing at the same time to be merged correctly, with no one's changes lost, so that collaboration is reliable.*  
Priority: P0 | Status: NOT STARTED

**US-016**  
*As an Editor, I want to see the cursor position of each collaborator in the document, labelled with their name, so that I know where they are working.*  
Priority: P1 | Status: NOT STARTED

**US-017**  
*As a Viewer, I want to see the document content in real time as Editors make changes, so that I can follow along without being able to accidentally edit.*  
Priority: P1 | Status: NOT STARTED

**US-018**  
*As any connected user, if I lose my network connection and reconnect, I want to receive the current document state automatically without refreshing the page.*  
Priority: P1 | Status: NOT STARTED

---

## Epic 5 — Presence

**US-019**  
*As a collaborator, I want to see the real names and avatar initials of everyone currently in the document so that I know who I am working with.*  
Priority: P1 | Status: NOT STARTED

**US-020**  
*As a collaborator, I want the presence list to update automatically when someone joins or leaves so that the information is always current.*  
Priority: P1 | Status: NOT STARTED

---

## Epic 6 — Persistence

**US-021**  
*As an Editor, I want my changes to be automatically saved so that I never lose work by forgetting to click Save.*  
Priority: P0 | Status: NOT STARTED

**US-022**  
*As an Editor, I want a visual indicator that tells me whether my latest changes have been saved to the server.*  
Priority: P1 | Status: NOT STARTED

**US-023**  
*As a document owner, if the server restarts while I am editing, I want my document content to be intact when I reconnect, up to within the last 30 seconds of edits.*  
Priority: P0 | Status: NOT STARTED

---

## Epic 7 — Version History

**US-024**  
*As a document owner, I want to view a list of saved document snapshots with their timestamps so that I can see the history of changes.*  
Priority: P1 | Status: NOT STARTED

**US-025**  
*As a document owner, I want to manually create a named snapshot before making a major change so that I have a restore point.*  
Priority: P2 | Status: NOT STARTED

**US-026**  
*As a document owner, I want to restore the document to a previous revision so that I can undo a large batch of unwanted changes.*  
Priority: P1 | Status: NOT STARTED

---

## Epic 8 — Security and Reliability

**US-027**  
*As a user, I want all communication with the server to happen over HTTPS and WSS so that my document content is encrypted in transit.*  
Priority: P0 | Status: NOT STARTED

**US-028**  
*As a user, I want the system to prevent abusive automated requests from slowing down the service for everyone.*  
Priority: P0 | Status: NOT STARTED

**US-029**  
*As an operator, I want a health check endpoint I can poll to verify the application, database, and Redis are all operational.*  
Priority: P1 | Status: NOT STARTED
