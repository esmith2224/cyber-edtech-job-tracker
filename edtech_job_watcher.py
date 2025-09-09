from __future__ import annotations

import csv
import datetime
import re
import sys
import time
from dataclasses import dataclass
from typing import List, Tuple
from urllib.parse import urljoin

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

    # Generic/public listings (formats vary; some may be JS-heavy)
    "Pearson": "https://pearson.jobs/search/?q=&location=remote",
    "HMH (Houghton Mifflin Harcourt)": "https://careers.hmhco.com/jobs",
    "ETS": "https://etscareers.searchsoft.net/PD/VacancyList.aspx",
    "Curriculum Associates": "https://www.curriculumassociates.com/about/careers",
    "NWEA": "https://www.nwea.org/about/careers/"
}

RAW_KEYWORDS = [
    "security", "cyber", "information security", "infosec", "iam",
    "risk", "grc", "compliance", "privacy", "security analyst",
    "security engineer", "trust", "vulnerability", "threat", "soc"
    # intentionally removed bare "ai" (too noisy)
]

# compile as whole-word/phrase patterns
KEYWORD_PATTERNS = [re.compile(rf"\b{re.escape(k)}\b", re.I) for k in RAW_KEYWORDS]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

TIMEOUT = 20
MAX_PER_SITE = 300  # safety cap


# ------------------ Core ------------------

@dataclass
class job:
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
    return any(p.search(t) for p in KEYWORD_PATTERNS)


def parse_greenhouse(company: str, html: str, base_url: str) -> List[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: List[Job] = []

    # Typical GH markup: div.opening > a, span.location
    for opening in soup.select("div.opening"):
        a = opening.select_one("a[href*='/job/']")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = urljoin(base_url, a.get("href") or "")
        if not title or not href:
            continue
        if not matches_keywords(title):
            continue
        loc_el = opening.select_one(".location") or opening.find(
            lambda tag: tag.name in ("span", "div")
            and tag.get("class")
            and any("location" in c.lower() for c in tag.get("class"))
        )
        loc = loc_el.get_text(strip=True) if loc_el else ""
        jobs.append(Job(company, title, loc, href))
        if len(jobs) >= MAX_PER_SITE:
            break

    # Fallback: sometimes GH pages use lists without .opening
    if not jobs:
        for a in soup.select("a[href*='/job/']"):
            title = a.get_text(strip=True)
            href = urljoin(base_url, a.get("href") or "")
            if title and href and matches_keywords(title):
                # try to grab a nearby location
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


def parse_generic(company: str, html: str, base_url: str) -> List[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: List[Job] = []
    for a in soup.select("a[href]"):
        title = a.get_text(" ", strip=True)
        href = a.get("href") or ""
        if not title or not href:
            continue
        # Heuristic: keyword match + looks like a job link
        if matches_keywords(title) and any(s in href.lower() for s in ("job", "career", "position", "opportunit")):
            abs_url = urljoin(base_url, href)
            jobs.append(Job(company, title, "", abs_url))
            if len(jobs) >= MAX_PER_SITE:
                break
    return jobs


def harvest_company(company: str, url: str) -> List[Job]:
    try:
        html = fetch(url)
    except Exception as e:
        print(f"[WARN] {company}: fetch failed: {e}", file=sys.stderr)
        return []

    if "boards.greenhouse.io" in url:
        return parse_greenhouse(company, html, url)
    else:
        return parse_generic(company, html, url)


def main():
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
