# Session Persistence Documentation

## Overview

This document describes the session persistence feature that allows the Agent Skills Framework web UI to maintain state when users switch tabs on mobile browsers.

## Problem Statement

When users switch to another tab on their mobile browser and then return to the skill-agent tab, the Server-Sent Events (SSE) connection is lost, and events don't resume being pushed from the server to the client.

## Solution

Implemented session persistence using:
- **localStorage** for client-side session ID storage
- **Session management** on the server to track state per session
- **Automatic reconnection** when page visibility is restored
- **Event tracking** to deliver only missed events

## Architecture

### Client-Side Components

1. **Session ID Generation**
   ```javascript
   function generateSessionId() {
       return Array.from(crypto.getRandomValues(new Uint8Array(16)))
           .map(b => b.toString(16).padStart(2, '0'))
           .join('');
   }
   ```

2. **localStorage Persistence**
   - Key: `agent_session_id`
   - Generated once and reused across page reloads
   - Survives tab switches and browser restarts

3. **Visibility Change Detection**
   ```javascript
   document.addEventListener('visibilitychange', function() {
       if (!document.hidden && sessionId && eventCount > 0) {
           reconnectToSession();
       }
   });
   ```

4. **Event Tracking**
   - `eventCount` tracks number of events received
   - Used to request only missed events during reconnection

### Server-Side Components

1. **Session Storage**
   ```python
   sessions = {
       'session_id': {
           'running': bool,
           'logs': [...],
           'chat_history': [...],
           'tools_called': [...],
           'start_time': timestamp,
           'elapsed_time': seconds,
           'completed': bool
       }
   }
   ```

2. **Session Cleanup**
   - Background thread runs every 10 minutes
   - Removes sessions older than 1 hour
   - Prevents unbounded memory growth

3. **API Endpoints**
   - `POST /api/run` - Start agent execution (requires session_id)
   - `POST /api/reconnect` - Resume session and get missed events

## Usage Flow

### Initial Connection

1. User loads the page
2. Client generates session ID using crypto API
3. Session ID stored in localStorage
4. User submits a query
5. Client sends request with session_id
6. Server creates session state
7. Events stream via SSE

### Tab Switch Away (Hidden)

1. Browser detects visibility change
2. May close SSE connection
3. Session state remains on server
4. Event count preserved on client

### Tab Switch Back (Visible)

1. Browser fires visibilitychange event
2. Client detects page is visible
3. Calls `/api/reconnect` with:
   - `session_id`: from localStorage
   - `last_event_index`: last received event number
4. Server sends missed events
5. Client continues displaying events seamlessly

## API Reference

### POST /api/run

Start agent execution with session persistence.

**Request:**
```json
{
  "input": "user query",
  "session_id": "abc123..."
}
```

**Response:** SSE stream of events

**Error Codes:**
- `400`: Missing session_id or input
- `500`: Agent initialization failed

### POST /api/reconnect

Reconnect to existing session and receive missed events.

**Request:**
```json
{
  "session_id": "abc123...",
  "last_event_index": 42
}
```

**Response:** SSE stream of missed events

**Error Codes:**
- `400`: Missing session_id
- `404`: Session not found (expired or never existed)

## Configuration

### Session Timeout

Default: 1 hour (3600 seconds)

Modify in `app.py`:
```python
SESSION_TIMEOUT = 3600  # 1 hour in seconds
```

### Cleanup Interval

Default: 10 minutes (600 seconds)

Modify in `app.py`:
```python
time.sleep(600)  # Run every 10 minutes
```

## Testing

### Manual Testing

1. Open the skill-agent web UI
2. Open browser console
3. Check session ID: `localStorage.getItem('agent_session_id')`
4. Start a query
5. Switch to another tab
6. Wait a few seconds
7. Switch back
8. Verify events continue streaming

### Automated Testing

```bash
# Test API endpoints
python tests/test_session_persistence.py

# Or run the comprehensive test
python /tmp/test_session_complete.py
```

## Security Considerations

1. **Session IDs**: Generated using `crypto.getRandomValues()` for cryptographic security
2. **Session Cleanup**: Prevents DoS via memory exhaustion
3. **No Sensitive Data**: Session state contains only execution logs
4. **CodeQL Verified**: 0 security vulnerabilities found

## Browser Compatibility

- ✅ Chrome/Edge (Chromium)
- ✅ Firefox
- ✅ Safari
- ✅ Mobile browsers (iOS Safari, Chrome Mobile)

Requires:
- localStorage support
- Page Visibility API
- crypto.getRandomValues()

All modern browsers support these features.

## Troubleshooting

### Session Not Persisting

1. Check localStorage is enabled
2. Verify session ID in console: `localStorage.getItem('agent_session_id')`
3. Check browser console for errors

### Events Not Resuming

1. Check session hasn't expired (1 hour timeout)
2. Verify network connectivity
3. Check browser console for reconnection errors
4. Verify `/api/reconnect` is being called (Network tab)

### Memory Issues

1. Monitor session count: check server logs
2. Verify cleanup thread is running
3. Adjust `SESSION_TIMEOUT` if needed

## Future Enhancements

Potential improvements:
- Configurable session timeout per user
- Session persistence to database for server restarts
- Multiple concurrent sessions per user
- Session export/import functionality
- WebSocket fallback for browsers without SSE support

## References

- [Page Visibility API](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API)
- [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [Web Crypto API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API)
- [localStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage)
