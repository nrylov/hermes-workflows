# Scheduling the daily digest

Ask Hermes in chat:

> Every day at 8 AM, run the feed-digest skill on examples/feeds.txt with a
> seen-file, and send me the briefing here.

Or via the CLI (see `hermes cron --help` for the exact flags on your version).
The script does the fetching; the scheduled agent only summarises, which keeps
each run cheap and the output reproducible.
