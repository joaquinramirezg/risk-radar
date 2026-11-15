# Deploying the site

The site is the `site/` folder, as is: no build step. Cloudflare Pages
serves it; `site/_headers` sets the security and cache headers.

## Option A: connect the GitHub repo (redeploys on every push)

Cloudflare dashboard → Workers & Pages → Create → Pages → Connect to Git →
pick the repo, then:

- Framework preset: None
- Build command: leave empty
- Build output directory: `site`

## Option B: upload from your machine

    npx wrangler pages deploy site --project-name risk-radar

## After the first deploy

- The link-preview tags in `site/index.html` (`og:image`, `og:url`) point at
  `https://risk-radar.pages.dev`. If Cloudflare gave the project another
  name, or you add a custom domain, change those two lines.
- Check the preview: paste the URL into https://www.opengraph.xyz or a
  LinkedIn post draft.
- `site/data/search.json` is about 10 MB (2.7 MB compressed); Pages allows
  25 MB per file and compresses it on the fly.

## Refreshing the data

    SEC_USER_AGENT="your-name your-email" make fetch
    make radar          # rebuild, findings, search index, consistency check
    node tools/og/render.js   # with `python3 -m http.server 8000` running at the repo root

The change-type labels need `ANTHROPIC_API_KEY` and
`python3 tools/classify_changes.py`, then `python3 tools/build_radar.py --relabel`.
