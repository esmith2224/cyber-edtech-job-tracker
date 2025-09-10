from __future__ import annotations

import csv
import datetime
import re
import sys
import time
from dataclasses import dataclass
from typing import List, Tuple
import requests
from bs4 import BeautifulSoup

# ------------------ Config ------------------

COMPANIES = {
    # Greenhouse-hosted
    "Amplify": "https://boards.greenhouse.io/amplify",
    "Instructure": "https://boards.greenhouse.io/instructure",
    "Khan Academy": "https://boards.greenhouse.io/khanacademy",
    "Duolingo": "https://boards.greenhouse.io/duolingo",
    "2U / edX": "https://boards.greenhouse.io/2u",
    "Quizlet": "https://boards.greenhouse.io/quizlet",
    "Chegg": "https://boards.greenhouse.io/chegg",
    "Coursera": "https://boards.greenhouse.io/coursera",

    # Generic/public listings (formats vary)
    "Pearson": "https://pearson.jobs/search/?q=&location=remote",
    "HMH (Houghton Mifflin Harcourt)": "https://careers.hmhco.com/jobs",
    "ETS": "https://etscareers.searchsoft.net/PD/VacancyList.aspx",
    "Curriculum Associates": "https://www.curriculumassociates.com/about/careers",
    "NWEA": "https://www.nwea.org/about/careers/",
}

KEYWORDS = [
    "security", "cyber", "information security", "infosec", "iam",
    "risk", "grc", "compliance", "privacy", "security analyst",
    "security engineer", "trust", "vulnerability", "threat", "soc", "ai",
]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

TIMEOUT = 20
MAX_PER_SITE = 300  # safety cap

# ------------------ Core ------------------


@dataclass
class Job:
    company: str
    title: str
    location: str
    url: str


def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def matches_keywords(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in KEYWORDS)


def parse_greenhouse(company: str, html: str) -> List[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: List[Job] = []
    # Look for job links on Greenhouse boards
    for a in soup.select("a[href*='/job/'], a[href*='boards.greenhouse.io']"):
        title = a.get_text(strip=True)
        href = a.get("href") or ""
        if href.startswith("/"):
            href = "https://boards.greenhouse.io" + href
        if title and href.startswith("http") and matches_keywords(title):
            # Try to find a nearby location node
            loc = ""
            loc_el = a.find_next(
                lambda tag: tag.name in ("span", "div")
                and tag.get("class")
                and any("location" in c.lower() for c in tag.get("class"))
            )
            if loc_el:
                loc = loc_el.get_text(strip=True)
            jobs.append(Job(company, title, loc, href))
            if len(jobs) >= MAX_PER_SITE:
                break
    return jobs


def parse_generic(company: str, html: str) -> List[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: List[Job] = []
    for a in soup.select("a"):
        title = a.get_text(" ", strip=True)
        href = a.get("href") or ""
        if not title or not href:
            continue
        # Simple heuristic: keyword match + job/career in URL
        if matches_keywords(title) and ("job" in href.lower() or "career" in href.lower()):
            # Make absolute if relative and origin is discoverable
            if href.startswith("/"):
                origin = ""
                base = soup.find("base")
                canon = soup.find("link", rel="canonical")
                m = None
                if base and base.get("href"):
                    m = re.match(r"(https?://[^/]+)", base.get("href"))
                if (not m) and canon and canon.get("href"):
                    m = re.match(r"(https?://[^/]+)", canon.get("href"))
                if m:
                    origin = m.group(1)
                if origin:
                    href = origin + href
            jobs.append(Job(company, title, "", href))
            if len(jobs) >= MAX_PER_SITE:
                break
    return jobs


def harvest_company(company: str, url: str) -> List[Job]:
    try:
        html = fetch(url)
    except Exception as e:
        print(f"[WARN] {company}: fetch failed: {e}", file=sys.stderr)
        return []
    if "greenhouse" in url:
        return parse_greenhouse(company, html)
    else:
        return parse_generic(company, html)


def main() -> None:
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    out_csv = f"it_cyber_jobs_{now}.csv"
    rows: List[Tuple[str, str, str, str]] = []

    for company, url in COMPANIES.items():
        print(f"Scraping {company} ...")
        jobs = harvest_company(company, url)
        for j in jobs:
            rows.append((company, j.title, j.location, j.url))
        time.sleep(1)  # be polite

    rows = sorted(set(rows))  # de-dup

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Company", "Title", "Location", "Link"])
        w.writerows(rows)

    print(f"Saved {len(rows)} jobs -> {out_csv}")
    if not rows:
        print("No matches today. Edit KEYWORDS or add more companies.")


if __name__ == "__main__":
    main()
