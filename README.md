# Teklon

Teklon is a static daily security news briefing. The front end reads `news.json`; GitHub Actions refreshes that file from public RSS sources, opens a pull request for review, and publishes merged changes from `main` to GitHub Pages. When an RSS item provides an HTTPS image, Teklon shows it on the story card and in the story detail.

## Daily review flow

At 06:15 UTC, `.github/workflows/daily-news.yml` collects items published that UTC day from CISA advisories, BleepingComputer, The Hacker News, OpenAI News, and Google AI. Recent earlier items are placed in the archive. The workflow creates or updates one pull request. When a maintainer approves that daily briefing, `.github/workflows/merge-approved-news.yml` merges it into `main` and publishes the resulting site in the same run.

The workflows use GitHub Actions' `GITHUB_TOKEN`. In repository settings, allow GitHub Actions to create pull requests and configure a ruleset or branch protection for `main` that requires at least one approval. The merge waits for GitHub's required branch rules. The approved-review workflow publishes the site directly because GitHub does not start a Pages workflow for a push made with `GITHUB_TOKEN`.

Every GitHub Action is pinned to a full commit SHA to comply with the repository's action policy. The Pages workflows package the deployment archive directly and upload it with the SHA-pinned `actions/upload-artifact` action, avoiding an unpinned nested action.

## Publish the site

In **Settings → Pages**, choose **GitHub Actions** as the build and deployment source. The `Publish Teklon website` workflow deploys ordinary pushes to `main`; approved automated briefing PRs are published by the merge-and-publish workflow. After the first merge, run **Prepare daily security briefing** once from the Actions tab to populate the first edition. GitHub Pages provides the public URL; a custom domain can be added in the same settings page.

## Run the feed collector locally

Requires Python 3.10 or newer and network access to the RSS sources:

```powershell
python scripts/fetch_news.py
```

The script only includes same-day stories on the landing page and retains up to 90 days of archive entries. The Archive navigation opens a separate view grouped by day; each edition expands on demand, with older stories revealed in small batches. The collector does not synthesize article details: summaries are plain-text excerpts from the source feeds, with the original article linked from each story.
