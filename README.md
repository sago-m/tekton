# Teklon

Teklon is a static daily security news briefing. The front end reads `news.json` and `videos.json`; GitHub Actions refreshes both files from public RSS and YouTube channel feeds, opens a pull request for review, and publishes merged changes from `main` to GitHub Pages. When an RSS item provides an HTTPS image, Teklon shows it on the story card and in the story detail.

The landing page also has a curated YouTube section, refreshed daily from official Google DeepMind and IBM Technology channels plus established cybersecurity educators John Hammond, LiveOverflow, and Computerphile. Video cards show the thumbnail, title, channel, and a short description; opening a card shows the channel-provided summary and a direct YouTube link. Edit `scripts/fetch_news.py` to change the curated channel list. The landing page also has a JSON-powered **My Blobs** carousel for approachable editorial guides. Edit `blobs.json` to add a blob, update its title, short description, image path, reading time, and numbered points. Illustration files live in `assets/blobs/`; each point can include an everyday example.

## Daily review flow

At 06:00 Europe/London time, `.github/workflows/daily-news.yml` collects items published that UTC day from CISA advisories, BleepingComputer, The Hacker News, OpenAI News, and Google AI. It also refreshes recent videos from official Google DeepMind and IBM Technology channels and established security educators John Hammond, LiveOverflow, and Computerphile. Recent earlier items are placed in the archive. When the feed changes, the workflow creates or updates one pull request, attempts to merge it automatically, and publishes the resulting site after a successful merge. GitHub's timezone-aware schedule keeps the run at 06:00 through UK daylight-saving changes.

The workflows use GitHub Actions' `GITHUB_TOKEN`. In repository settings, allow GitHub Actions to create pull requests. If the `main` ruleset blocks the automatic merge, the daily PR stays open for the approval workflow. Add a repository secret named `DAILY_MERGE_TOKEN` with an administrator token to let the daily workflow bypass the approval rules; otherwise, set the main ruleset to require zero approvals (this affects every PR). The daily workflow publishes the site directly because GitHub does not start another Pages workflow for a push made with `GITHUB_TOKEN`.

Every GitHub Action is pinned to a full commit SHA to comply with the repository's action policy. The Pages workflows package the deployment archive directly and upload it with the SHA-pinned `actions/upload-artifact` action, avoiding an unpinned nested action.

## Publish the site

In **Settings → Pages**, choose **GitHub Actions** as the build and deployment source. The `Publish Teklon website` workflow deploys ordinary pushes to `main`; the daily briefing workflow publishes its own automatic merge. After the first merge, run **Refresh and publish daily security briefing** once from the Actions tab to populate the first edition. GitHub Pages provides the public URL; a custom domain can be added in the same settings page.

## Run the feed collector locally

Requires Python 3.10 or newer and network access to the RSS sources:

```powershell
python scripts/fetch_news.py
```

The script only includes same-day stories on the landing page and retains up to 90 days of archive entries. The Archive navigation opens a separate view grouped by day; each edition expands on demand, with older stories revealed in small batches. The collector does not synthesize article details: summaries are plain-text excerpts from the source feeds, with the original article linked from each story.
