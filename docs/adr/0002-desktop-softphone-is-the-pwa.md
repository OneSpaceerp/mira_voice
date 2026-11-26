# 0002 — The desktop softphone is the installable Mira Desk PWA

- Status: accepted
- Date: 2026-11-25

## Context
The study planned a Flutter desktop app. The project now has PWA skills, Mira Desk is already a browser app with a WebRTC softphone, and the team is one developer.

## Decision
At MVP, Windows and macOS agents install Mira Desk as a PWA. Flutter is used for Android and iOS (Mira Phone), where native call UI and push wake-up need native code. A Flutter desktop build is reconsidered only if the PWA cannot meet a requirement (e.g. global hotkeys, USB headset buttons).

## Consequences
One less app to build and update. Must test headset and notification behaviour in Chrome and Edge on Windows.
