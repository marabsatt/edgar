import re
import os
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


SECTION_PATTERNS = {
    "Item 1": r"Item\s+1\.?\s+Business",
    "Item 1A": r"Item\s+1A\.?\s+Risk\s+Factors",
    "Item 7": r"Item\s+7\.?\s+Management[’']s\s+Discussion",
    "Item 7A": (
        r"Item\s+7A\.?\s+Quantitative\s+and\s+Qualitative\s+Disclosures"
        r"\s+About\s+Market\s+Risk"
    ),
}

EMAIL = os.environ.get('EMAIL')


def extract_sections(url: str, max_chars: int = 15_000) -> dict[str, str]:
    """Extract configured Item sections from an HTML SEC filing.

    SEC filings commonly repeat Item headings in their table of contents. For
    each Item, this function collects every candidate and keeps the longest
    match, which should be the filing's body section rather than its ToC entry.
    """
    response = requests.get(
        url,
        headers={f"User-Agent": "SecResearchAssistant {EMAIL}"},
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    text = soup.get_text(separator="\n", strip=True)
    text_clean = text.replace("\xa0", " ")
    sections: dict[str, str] = {}

    for item, title_pattern in SECTION_PATTERNS.items():
        pattern = re.compile(
            rf"({title_pattern}[\s\S]+?)(?=\n\s*Item\s+\d{{1,2}}[A-Z]?\.?\b|\Z)",
            re.IGNORECASE,
        )
        matches = list(pattern.finditer(text_clean))

        if matches:
            longest_match = max(matches, key=lambda match: len(match.group(1)))
            sections[item] = longest_match.group(1).strip()[:max_chars]

    return sections


def get_latest_ten_k_url(ticker_symbol: str) -> str:
    """Return the first available 10-K URL reported by yfinance."""
    ticker = yf.Ticker(ticker_symbol)
    for filing in ticker.sec_filings:
        exhibits = filing.get("exhibits") or {}
        ten_k_url = exhibits.get("10-K")
        if ten_k_url:
            return ten_k_url

    raise ValueError(f"No 10-K filing found for {ticker_symbol}.")

def url_to_pdf(url: str, output_path: str):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        # Wait until network requests finish so dynamic content loads
        page.goto(url, wait_until="networkidle")
        
        page.pdf(
            path=output_path,
            format="A4",
            print_background=True,
            margin={"top": "20mm", "bottom": "20mm", "left": "20mm", "right": "20mm"}
        )
        browser.close()

if __name__ == "__main__":
    filing_url = get_latest_ten_k_url("MSFT")
    url_to_pdf(url = filing_url,
               output_path = "/Users/mitchelrabsatt/Developer/edgar/src/edgar/filings/MSFT_10K.pdf")
    print(extract_sections(filing_url))
