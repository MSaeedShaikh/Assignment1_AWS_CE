# External API -- Ticketmaster Discovery API

## Comparison Table

| API | Free Tier | Auth | Required Fields Available | Verdict |
|---|---|---|---|---|
| **Ticketmaster Discovery** | 5,000 req/day, 5 req/sec | API key (query param) | name, date, venue, city, image (16:9), URL, classification | **Selected** |
| Eventbrite | 2,000 req/day | OAuth 2.0 (token exchange) | name, date, venue, city, URL — no standardised images | Rejected |
| PredictHQ | 1,000 req/month | Bearer token (approval required) | name, date, category, rank — no images, no venue detail | Rejected |

---

## Why Ticketmaster

- **API key simplicity** -- authentication is a single query parameter (`apikey=...`); there is no OAuth token exchange, no client secret, and no redirect URI to configure, making it straightforward to integrate within a student project timeline and easy to rotate by updating one environment variable.
- **Required field coverage** -- the Discovery API response includes every field the application extracts: `name`, `dates.start.localDate`, `_embedded.venues[0].name`, `_embedded.venues[0].city.name`, a structured `images` array with aspect-ratio metadata (`16_9`), and a direct `url` to the event page -- no extra transformation or secondary API calls are needed.
- **Free tier limits** -- 5,000 requests per day and 5 per second is more than sufficient for a 15-minute polling interval (96 requests per day) and accommodates bursts during testing without hitting a rate-limit wall.
- **Documentation quality** -- the Ticketmaster Developer Portal provides an interactive API Explorer, field-level schema documentation, and code examples, which significantly reduced integration time compared to Eventbrite's OAuth flow and PredictHQ's approval-gated onboarding.
- **Accessibility without approval** -- a Ticketmaster developer account and API key are issued immediately on registration; PredictHQ requires manual approval for access to event data, which introduces an unpredictable delay incompatible with an assignment deadline.

---

## Sample API Response

The following is a simplified representation of a single event object as returned by `GET /discovery/v2/events.json`. Only the fields extracted by `fetch_events()` are shown.

```json
{
  "name": "Taylor Swift | The Eras Tour",
  "url": "https://www.ticketmaster.com/event/Z7r9jZ1A7uGdf",
  "dates": {
    "start": {
      "localDate": "2025-07-14"
    }
  },
  "images": [
    {
      "ratio": "16_9",
      "url": "https://s1.ticketm.net/dam/a/example_16_9.jpg",
      "width": 1024,
      "height": 576
    },
    {
      "ratio": "3_2",
      "url": "https://s1.ticketm.net/dam/a/example_3_2.jpg",
      "width": 305,
      "height": 203
    }
  ],
  "info": "Doors open 90 minutes before showtime. No re-entry.",
  "_embedded": {
    "venues": [
      {
        "name": "Friends Arena",
        "city": {
          "name": "Stockholm"
        }
      }
    ]
  }
}
```

The application selects the first image whose `ratio` equals `"16_9"` using `next((img['url'] for img in images if img.get('ratio') == '16_9'), None)`, falling back to `None` if no 16:9 image is present. The `info` field is used as the event description and defaults to an empty string if absent.

---

## Integration Details

**Polling interval** -- `fetch_events()` is scheduled via APScheduler's `BackgroundScheduler` at a 15-minute interval (`trigger='interval', minutes=15`). This was chosen to balance data freshness against the free-tier quota: 96 requests per day (one every 15 minutes) is well within the 5,000 request daily limit, leaving headroom for ad-hoc testing and any retry attempts following transient failures.

**Cache design** -- parsed events are stored in a module-level `EVENTS_CACHE` list. The list is replaced atomically on each successful fetch, so a Flask worker reading the list mid-update will see either the previous complete list or the new complete list -- never a partial result. The trade-off is that each EC2 instance maintains an independent in-memory cache; if the two instances' 15-minute cycles drift out of phase they may briefly serve different event sets. For a read-only display portal this is acceptable. A shared cache (ElastiCache, S3 JSON file) would eliminate the drift at the cost of additional infrastructure.

**Error handling** -- `fetch_events()` wraps the entire HTTP call and parse loop in a `try/except Exception` block. On failure it prints a timestamped error message to stdout (captured by Gunicorn's log) and leaves `EVENTS_CACHE` unchanged, so users continue to see the last successfully fetched events rather than an empty page or a 500 error. `response.raise_for_status()` is called before parsing to ensure non-2xx responses (e.g. 429 rate-limit, 401 invalid key) are treated as exceptions and logged rather than silently producing malformed data.
