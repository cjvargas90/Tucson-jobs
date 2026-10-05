import os, json, re, html, datetime
from urllib.parse import urlparse
import requests

# ---------------- SETTINGS (safe to edit) ----------------
LOCATION = "Tucson, Arizona, United States"
SEARCHES = ["marketing", "communications", "partnership marketing"]
INCLUDE = ["marketing", "communications", "partnership", "sponsorship", "content",
           "digital", "brand", "social media", "public relations", "web"]
EXCLUDE = ["intern", "internship", "sales associate", "sales representative",
           "account executive", "telemarketing", "door to door", "cashier", "driver"]
KEEP_DAYS = 30
# ----------------------------------------------------------

AGGREGATORS = ["linkedin", "indeed", "glassdoor", "ziprecruiter", "monster", "simplyhired",
               "talent.com", "jooble", "lensa", "adzuna", "careerbuilder", "bebee",
               "jobright", "salary.com", "learn4good", "jobleads", "snagajob", "google"]
SEEN_FILE = "seen.json"
OUT_FILE = "docs/index.html"
API_KEY = os.environ["SERPAPI_KEY"]


def has_word(text, words):
    return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)


def wanted(title):
    t = title.lower()
    return has_word(t, INCLUDE) and not has_word(t, EXCLUDE)


def fetch(query):
    params = {"engine": "google_jobs", "q": query, "location": LOCATION,
              "hl": "en", "gl": "us", "api_key": API_KEY}
    r = requests.get("https://serpapi.com/search.json", params=params, timeout=60)
    data = r.json()
    if "error" in data:
        if "hasn't returned any results" in data["error"]:
            return []
        raise RuntimeError(data["error"])
    return data.get("jobs_results", [])


def best_link(job):
    opts = job.get("apply_options", [])
    for o in opts:
        domain = urlparse(o.get("link", "")).netloc.lower()
        if domain and not any(a in domain for a in AGGREGATORS):
            return o["link"], "Apply on employer site"
    if opts:
        return opts[0]["link"], "Apply via " + opts[0].get("title", "job board")
    return job.get("share_link", "#"), "View on Google Jobs"


def job_key(title, company):
    return re.sub(r"\W+", "", (title + "|" + company).lower())


def card(j, is_new):
    e = html.escape
    desc = j["description"]
    short = desc[:350] + ("…" if len(desc) > 350 else "")
    badge = '<span class="new">NEW</span> ' if is_new else ""
    meta = " · ".join(x for x in [j["company"], j["location"], j["salary"], j["posted"]] if x)
    return f"""
<div class="job">
  <h3>{badge}{e(j['title'])}</h3>
  <p class="meta">{e(meta)} · first seen {e(j['first_seen'])}</p>
  <p>{e(short)}</p>
  <details><summary>Full description</summary><p class="full">{e(desc)}</p></details>
  <a class="btn" href="{e(j['link'])}" target="_blank" rel="noopener">{e(j['link_label'])}</a>
</div>"""


def main():
    today = datetime.date.today().isoformat()
    seen = json.load(open(SEEN_FILE)) if os.path.exists(SEEN_FILE) else {}
    errors = []

    for q in SEARCHES:
        try:
            results = fetch(q)
        except Exception as ex:
            errors.append(f"Search '{q}' failed: {ex}")
            continue
        for job in results:
            title = job.get("title", "")
            company = job.get("company_name", "")
            if not wanted(title):
                continue
            k = job_key(title, company)
            ext = job.get("detected_extensions", {})
            link, label = best_link(job)
            entry = seen.get(k, {"first_seen": today})
            entry.update({
                "title": title, "company": company,
                "location": job.get("location", ""),
                "salary": ext.get("salary", ""),
                "posted": ext.get("posted_at", ""),
                "description": job.get("description", ""),
                "link": link, "link_label": label, "last_seen": today,
            })
            seen[k] = entry

    cutoff = (datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
    seen = {k: v for k, v in seen.items() if v.get("last_seen", today) >= cutoff}

    new = [v for v in seen.values() if v["first_seen"] == today]
    older = sorted([v for v in seen.values() if v["first_seen"] != today],
                   key=lambda v: v["first_seen"], reverse=True)

    err_html = "".join(f'<p class="err">{html.escape(m)}</p>' for m in errors)
    page = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Tucson Marketing Jobs</title>
<style>
 body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; max-width: 820px; margin: 2em auto; padding: 0 1em; color: #222; }}
 h1 {{ color: #003366; margin-bottom: 0; }}
 .updated {{ color: #666; margin-top: .3em; }}
 h2 {{ border-bottom: 2px solid #003366; padding-bottom: .2em; margin-top: 1.6em; }}
 .job {{ border: 1px solid #ddd; border-radius: 8px; padding: 1em 1.2em; margin: 1em 0; }}
 .job h3 {{ margin: 0 0 .3em; }}
 .meta {{ color: #555; font-size: .92em; margin: 0 0 .6em; }}
 .new {{ background: #c8102e; color: #fff; font-size: .7em; padding: .15em .5em; border-radius: 4px; vertical-align: middle; }}
 .btn {{ display: inline-block; background: #003366; color: #fff; padding: .45em 1em; border-radius: 6px; text-decoration: none; margin-top: .4em; }}
 .full {{ white-space: pre-wrap; font-size: .92em; }}
 .err {{ background: #fff3cd; padding: .6em; border-radius: 6px; }}
</style></head><body>
<h1>Tucson Marketing Jobs</h1>
<p class="updated">Last updated {today} · {len(new)} new today · {len(seen)} total from the past {KEEP_DAYS} days</p>
{err_html}
<h2>New today</h2>
{''.join(card(j, True) for j in new) or '<p>No new jobs today.</p>'}
<h2>Earlier this month</h2>
{''.join(card(j, False) for j in older) or '<p>Nothing yet.</p>'}
</body></html>"""

    os.makedirs("docs", exist_ok=True)
    with open(OUT_FILE, "w") as f:
        f.write(page)
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f, indent=1)


if __name__ == "__main__":
    main()
