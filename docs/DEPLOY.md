# Deploying the site

The site is the `site/` folder, as is: no build step. Vercel serves it;
`vercel.json` at the repo root sets the output directory and the security
and cache headers.

## Option A: import the GitHub repo (redeploys on every push to master)

vercel.com → Add New Project → import `joaquinramirezg/risk-radar`. The
settings come from `vercel.json`; leave Framework as Other and the build
command empty.

## Option B: deploy from your machine

    npx vercel --prod

## After the first deploy

- The link-preview tags in `site/index.html` (`og:image`, `og:url`) must
  point at the production URL. If Vercel gives the project another name, or
  you add a custom domain, change those two lines.
- Check the preview: paste the URL into https://www.opengraph.xyz or a
  LinkedIn post draft.
- `site/data/search.json` is about 10 MB (2.7 MB compressed); Vercel
  serves it compressed.

## Refreshing the data

    SEC_USER_AGENT="your-name your-email" make fetch
    make radar          # rebuild, findings, search index, consistency check
    node tools/og/render.js   # with `python3 -m http.server 8000` running at the repo root

The change-type labels need `ANTHROPIC_API_KEY` and
`python3 tools/classify_changes.py`, then `python3 tools/build_radar.py --relabel`.
