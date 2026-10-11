# HomeCircle meeting feed

A free, static daily feed of Alcoholics Anonymous and Narcotics Anonymous meetings for the HomeCircle recovery app. Australia is the first country. Another country is a registry entry, not a new app.

HomeCircle is not affiliated with Alcoholics Anonymous World Services, the Australian General Service Office, or Narcotics Anonymous. The feed is a cache of meeting lists those service bodies already publish for meeting finders. It does not collect them from search engines.

## What the apps fetch

| File | Contents |
| --- | --- |
| `dist/feed/au/index.json` | Publish index. Apps fetch the copy at `https://lendrody28-spec.github.io/homecircle/feed/au/index.json` |
| `dist/feed/au/<STATE>.json` | Minified state shards, plus `online.json` and `unknown.json`. Each file stays under 900 KB |
| `dist/au/meetings.json` | Full Australia snapshot used to build the shards and the changes report |
| `dist/au/coverage.json` | Counts from the last build |
| `dist/changes/au/latest.json` | Added, removed, changed, and broken join links |
| `dist/feed-items.json` | Curated cards that a person has approved |

The client contract is [clients/SPEC.md](clients/SPEC.md). Sample fetch and Live now code:

- [clients/swift/MeetingFeed.swift](clients/swift/MeetingFeed.swift)
- [clients/kotlin/MeetingFeed.kt](clients/kotlin/MeetingFeed.kt)

Reference behaviour, covered by tests: `src/homecircle_feed/live.py`.

## Meeting record

```json
{
  "id": "na:au:3783",
  "fellowship": "NA",
  "name": "Albany Sunday Night",
  "schedule": {
    "day": "sunday",
    "weekday": 0,
    "start": "17:00",
    "timezone": "Australia/Perth",
    "timezone_source": "source",
    "duration_minutes": 60
  },
  "format": "in_person",
  "location": {
    "name": "Uniting Church - Lesser Hall",
    "address": "12 Duke Street",
    "suburb": "Albany",
    "state": "WA",
    "postal_code": "6330",
    "country": "AU",
    "latitude": -35.026241,
    "longitude": 117.880904,
    "approximate": false
  },
  "online": {"url": null, "phone": null},
  "tags": ["open"],
  "notes": null,
  "source": {
    "id": "na-au-bmlt",
    "name": "NA Australia BMLT",
    "url": "https://www.na.org.au/main_server/",
    "record_url": null,
    "last_seen": "2026-10-06T16:00:00+00:00"
  }
}
```

`weekday` is 0 on Sunday through 6 on Saturday. `format` is `in_person`, `online`, or `hybrid`. Tags, only when the source says so, are `open`, `closed`, `women`, `men`, `lgbtq`, `first_nations`, and `families`.

`timezone_source` says where the IANA zone came from:

- `source` — the meeting record named a zone, and it was not the website's default
- `state` — inferred from NSW, VIC, QLD, SA, WA, TAS, NT, or ACT
- `country_default` — nothing better was available

AA Australia's site timezone is `Australia/Sydney`, and that value is stamped on most meetings, including Queensland and Western Australia. During daylight saving that would make a Brisbane meeting look an hour early. Those rows are retimed from the state. A meeting that explicitly says `Australia/Perth` or `Australia/Brisbane` keeps that zone.

The JSON Schema is [schemas/meetings.schema.json](schemas/meetings.schema.json).

## Sources that worked

Checked on 6 October 2026. Both fetches are one JSON request per source per day, with a named user agent, robots.txt checked first, and at least one second between requests to the same host. Responses are cached for 12 hours. Contact names, group emails, admin notes, editor logins, and `edit_url` values are not copied. Email addresses inside public notes are replaced with `[email removed]`.

### NA Australia — used

[BMLT semantic API](https://www.na.org.au/main_server/semantic) at `https://www.na.org.au/main_server/`. This is root `124` in the public [aggregator server list](https://raw.githubusercontent.com/bmlt-enabled/aggregator/refs/heads/main/serverList.json). BMLT publishes this API for meeting lists. CORS is open and no key is required.

`https://www.na.org.au/robots.txt` disallows `/meetings/` and does not disallow `/main_server/`. The job only calls `/main_server/client_interface/json/`. The field list omits contact and admin columns. `GetServerInfo` is not called, because that response can contain a geocoder key.

### AA Australia — used

Meeting Guide / TSML feed published by the 12 Step Meeting List plugin:

`https://meetings.aa.org.au/wp-json/tsml/meetings`

The [Meeting Guide spec](https://github.com/code4recovery/spec) says the format is non-proprietary and other systems are encouraged to use it. `robots.txt` disallows `/wp-admin/` except `admin-ajax.php`. The feed URL is allowed. The response sends `x-robots-tag: noindex`, which asks search engines not to index that URL. It does not forbid this cache.

Online and hybrid AA meetings are in the same feed (`conference_url`, `conference_phone`, `attendance_option`). There is no second AA online list to merge.

The plugin's site timezone is `Australia/Sydney` (`timezone_string` on `/wp-json/`). Per-meeting zones that only repeat that default are replaced from the state, as described above.

## Sources not used

| Source | Why it is off |
| --- | --- |
| BMLT aggregator `https://aggregator.bmltenabled.org/main_server/` | Repeats every regional root. The daily job uses the Australian root so the same meetings are not downloaded twice. `robots.txt` on the aggregator returned 404, which would have allowed a fetch. |
| Virtual NA `https://bmlt.virtual-na.org/main_server/` | Public BMLT root for location-agnostic online NA meetings. Country is not reliable, and Australian online meetings are already on the NA Australia root. |
| AA Online Intergroup `https://aa-intergroup.org/meetings/` | `robots.txt` returned a bot challenge. No Meeting Guide JSON link was verified. Their central-query API is not documented here as a public reuse feed. |
| Search engines | Not used. |

The same notes are in [sources/registry.json](sources/registry.json) under `not_used`.

## Australia coverage

The last build writes the exact counts to `dist/au/coverage.json`. From the fetch used to produce this repository:

<!-- COVERAGE_START -->
Built 6 October 2026 from the two sources above.

| | |
| --- | ---: |
| Meetings published | 2,922 |
| AA | 2,161 of 2,228 fetched |
| NA | 761 of 761 fetched |
| In person | 2,356 |
| Online | 431 |
| Hybrid | 135 |
| With a map pin | 2,912 |
| With a join URL | 547 |
| With a dial-in number | 218 |

By state: NSW 1,123, VIC 639, QLD 619, WA 246, SA 148, ACT 61, TAS 52, NT 24. Ten NA rows have no state: seven "Downunder Marathon" meetings were pinned on the BMLT map centre (that pin is dropped), and three others had no province and a pin outside Australia.

Every Queensland meeting in the file is `Australia/Brisbane`. Western Australia is `Australia/Perth`, South Australia `Australia/Adelaide`, the Northern Territory `Australia/Darwin`, Tasmania `Australia/Hobart`. Two Victorian rows and one New South Wales row keep a zone the source set explicitly.

Tags the sources actually set: open 1,053, women 163, closed 86, men 76, lgbtq 68, first_nations 14. No families/partners tag this run. The AA feed had no `AL-AN` or `AL` codes, and the NA Australia format list has no families code. The parser still maps those codes when a source sends them.

Left out: 57 inactive AA meetings and 10 AA meetings tagged temporarily closed. No unpublished NA rows were returned.

Join links checked: 321 unique URLs. 299 responded, 21 were refused by the host (counted as blocked, not removed), and 1 is broken: `https://bluejeans.com/703284722/7733` (Newcastle Just For Today) no longer resolves.
<!-- COVERAGE_END -->

Inactive AA meetings and meetings tagged `TC` (location temporarily closed) are left out of the file and counted under `withheld`. Unpublished NA meetings are left out. A failed source does not wipe the previous rows from that source; the changes report lists it under `stale_sources` and those rows keep their old `last_seen`.

## Schedule

GitHub Actions cron is UTC. 02:00 in Australia/Brisbane is 16:00 UTC, all year, because Brisbane does not use daylight saving.

```cron
0 16 * * *
```

The workflow is [.github/workflows/daily-feed.yml](.github/workflows/daily-feed.yml). It runs the tests, rebuilds `dist/`, and commits the JSON when something changed. `workflow_dispatch` runs the same job by hand. GitHub may start a scheduled job late. The feed does not depend on the minute.

Actions minutes are free on a public repository.

## Run it locally

Python 3.11 or newer. No third-party packages.

```bash
python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m homecircle_feed build --refresh
```

`--skip-link-check` skips HEAD/GET probes of join URLs. The daily job runs that check. HTTP 404, 410, and 5xx, plus DNS and timeouts, are broken. HTTP 401, 403, and 429 are recorded as blocked by the host (Zoom often does this) and are not listed as removed meetings.

## Host the JSON for nothing

The apps should use a URL that sends `Access-Control-Allow-Origin` if a website will read it. Native iOS and Android clients do not need CORS.

1. **GitHub Pages.** Copy `dist/feed/` onto the site so it is served at `/feed/`. The HomeCircle Pages URL is `https://lendrody28-spec.github.io/homecircle/feed/au/index.json`.
2. **jsDelivr.** For a public GitHub repo, `https://cdn.jsdelivr.net/gh/<owner>/<repo>@gh-pages/feed/au/index.json` caches that same tree.
3. **Cloudflare Pages or Netlify.** Upload the `dist/feed/` directory. No build command.

The nightly job writes `dist/feed/au/` beside the full `dist/au/meetings.json` snapshot. Publish the `feed/` tree. State files are minified and each stays under 900 KB.

`raw.githubusercontent.com` is a poor app URL: it is rate limited and does not send CORS headers.

Commit `dist/` so the host is just static files. The workflow already does that.

## Curated news

`curated/feed-items.json` holds drafts for AA Australia, NA Australia, and Lifeline. Each item has `approved`. The build copies only `approved: true` into `dist/feed-items.json`. A missing or non-boolean flag fails the build. Review notes are not published.

The three seeded cards are unapproved on purpose. Nothing from those organisations is posted until a person has read it and set the flag. The job does not scrape their news pages.

## Add a country

1. Find the NA root in the aggregator `serverList.json`, or a Meeting Guide JSON URL the area actually publishes.
2. Read that host's `robots.txt`. If the feed path is disallowed, do not add it.
3. Append a country to `sources/registry.json` with `"enabled": true`, a default IANA timezone, and one or more `bmlt` or `tsml` sources.
4. Run `python3 -m homecircle_feed build --country NZ`.

The job writes `dist/nz/meetings.json` the same way. State-to-timezone inference is Australian. Other countries keep the zone on the record, or the country's `default_timezone` when the record has none.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Parsers, timezone correction, robots longest-match, the changes report, offline cache fallback, Live now across midnight and across Brisbane/Sydney daylight saving, unapproved feed items, and a failed source keeping yesterday's rows.

## Privacy

Join URLs, dial-in numbers, venue, suburb, and public notes stay, because that is how someone attends. Personal emails, contact names, editor accounts, and admin notes do not. Do not point this job at `GetServerInfo` on a root you have not checked: some roots echo a geocoder key there.
