# HomeCircle meeting feed client

The apps fetch JSON. They do not call BMLT or the AA site themselves.

## Files

Australia is published as small minified files. Start here:

`https://lendrody28-spec.github.io/homecircle/feed/au/index.json`

| File | Use |
| --- | --- |
| `au/index.json` | `meeting_count`, `sources` (id, name, url), and `states` |
| `au/NSW.json` (and the other states) | Meetings in that state, including online meetings that name the state |
| `au/NSW-1.json`, `au/NSW-2.json` | Used only when one state file would be over 900 KB. `states[].file` is the real name |
| `au/online.json` | Every meeting with `format` `online`, with or without a state |
| `au/unknown.json` | Rows with no state. Present only when `states` lists it |
| `feed-items.json` | Curated cards. Empty until a person sets `approved` to true |

`states` is an array of `{state, file, meeting_count}`. `state` is `NSW`, `VIC`, `QLD`, `WA`, `SA`, `TAS`, `ACT`, `NT`, `online`, or `unknown`. Fetch every entry whose `state` is the user's state (there may be more than one file), and also fetch `online.json` when it is listed.

On open:

1. Fetch `index.json`. If that fails, read the cached index. If there is no cache, show an offline empty state.
2. Fetch the user's state file or files, plus `online.json`.
3. Write each response to disk before showing it.
4. If a file request fails, use that file's cache.
5. Merge by `id` so an online meeting that appears in both the state file and `online.json` is shown once.

A feed older than 48 hours is still usable. Show it, and say that the list may be out of date.

Each state file and `online.json` is one JSON object with `schema_version`, `country`, `generated_at`, `meeting_count`, `sources`, and `meetings`. The files are minified. `sources` on the wrapper has `id`, `name`, and `url`. Each meeting's `source` has only `id`, `record_url`, and `last_seen`.

## Meeting

`weekday` is 0 for Sunday through 6 for Saturday. `start` is 24-hour `HH:MM` in `timezone` (an IANA name such as `Australia/Brisbane`). `duration_minutes` is how long that occurrence runs.

`format` is `in_person`, `online`, or `hybrid`.

`tags` is a subset of `open`, `closed`, `women`, `men`, `lgbtq`, `first_nations`, `families`. Absence of `open` or `closed` means the source did not say.

`location.approximate` true means the pin is a suburb centroid, usually an online meeting.

`online.url` and `online.phone` are the join details. Group emails and personal numbers are not in the file.

## Live now / starting soon

Do this on the device. The feed does not contain a "live" flag.

1. Take the current instant.
2. Interpret `start` and `weekday` in the meeting's timezone, not the phone's timezone.
3. **Live now:** the latest start that is still at or before now, and now is before start plus `duration_minutes`. A Saturday 23:30 meeting with a 90 minute duration is live at Sunday 00:15.
4. **Starting soon:** not live, and the next start is within 30 minutes.

The end is exclusive: a 60 minute meeting that started at 17:00 is no longer live at 18:00.

`src/homecircle_feed/live.py` is the reference. The Swift and Kotlin samples follow it.

## Feed items

Render `feed-items.json` `items` only. The build has already dropped unapproved drafts. Do not scrape AA, NA, or Lifeline inside the app.
