# Ad Hook Machine

**Give it a number and an offer. It writes N direct-response hooks, renders N ad images, and builds the Meta campaign upload.**

```
N quotes (real emotional language scraped from discussions)
  → N headlines (Claude, rewritten as direct-response hooks, checked against competitor ads)
  → N 1080×1080 images (Pillow, pixel-perfect text fitting)
  → Meta Ads Manager bulk-upload sheet + campaign folder
```

Example output from a home-services test campaign is in [`examples/sample-campaign/`](examples/sample-campaign/).

## What it does

- **Voice-of-customer scraping** (`quote_scraper.py`, `browser_scraper.py`): pulls real complaints and phrases people use, so hooks sound human
- **Competitor-aware** (`competitor_data_puller.py`, `hook_analyzer.py`): reads the Facebook Ad Library for the niche and steers away from the angles everyone is already running
- **Headline engine** (`headline_generator.py`): Claude, prompted with classic direct-response headline frameworks, with a uniqueness check across the batch
- **Deterministic creative** (`image_generator.py`, `font_calculator.py`, `row_formatter.py`): no image-model cost and no garbled text. Font size and line breaks are solved so every headline fills the frame
- **Multi-offer**: spreads hooks evenly across several offers from `offers.txt`
- **Performance loop** (`performance_analyzer.py`): reads results back so the next batch leans into what's winning
- **Advanced agents** (`advanced/`): a thinking agent, a vision critic, product scraping and Perplexity research tools

## Stack

`python` `claude` `openai` `pillow` `playwright` `meta-ads` `perplexity`

## Run

```bash
pip install -r requirements.txt
cp api_keys.example.txt api_keys.txt    # git-ignored; env vars also work
python hook_generator/main.py
```

Keys are loaded by `hook_generator/api_keys.py` from the git-ignored `api_keys.txt` or from environment variables. None are committed.
