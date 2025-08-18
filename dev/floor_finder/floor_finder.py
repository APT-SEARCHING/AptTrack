from playwright.sync_api import sync_playwright
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# url = "https://www.equityapartments.com/san-francisco-bay/north-san-jose/vista-99-apartments?mkwid=sSEfiPgbX_dc&pcrid=494631032773&pkw=vista%2099%20apartments%20santa%20clara&pmt=e&utm_source=google&utm_medium=cpc&utm_term=vista+99+apartments+santa+clara&utm_campaign=&utm_group=Vista+99+Apartments&gclsrc=aw.ds&&utm_source=google&utm_medium=cpc&utm_campaign=EQR_San+Francisco_Properties_Search_Branded_Exact_Null&mkwid=sSEfiPgbX&pcrid&494631032773&pkw&vista%2099%20apartments%20santa%20clara&pmt&e&pdv&c&slid&&product&&pgrid&41086285352&ptaid&kwd-361782048603&&pgrid=41086285352&ptaid=kwd-361782048603&utm_content=sSEfiPgbX&pcrid&494631032773&pkw&vista%2099%20apartments%20santa%20clara&pmt&e&pdv&c&slid&&product&&pgrid&41086285352&ptaid&kwd-361782048603&&intent=San+Francisco_b&gad_source=1&gad_campaignid=777233997&gbraid=0AAAAAD80QHtAu8cOSPYj_GsH28Ai7vRo6&gclid=Cj0KCQjwnovFBhDnARIsAO4V7mC7jJmAqHDO96KzKo2NnK4nDX-yGOnx93UU7ztr8iEi_uowMwb_eH4aArN_EALw_wcB"

url = 'https://www.irvinecompanyapartments.com/locations/northern-california/santa-clara/santa-clara-square.html'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)  # Set to False to see what's happening
    page = browser.new_page()
    
    print("Navigating to the page...")
    page.goto(url)
    
    # Wait for any content to load and stabilize
    time.sleep(5)
    
    print("Getting page content...")
    html = page.content()
    
    # Save the HTML for debugging
    # with open("output.txt", "w", encoding="utf-8") as f:
    #     f.write(html)
    
    # Parse with BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    
    # Get text content (first 1000 chars)
    # txt = soup.get_text(separator="\n", strip=True)
    # with open("output.txt", "w", encoding="utf-8") as f:
    #     f.write(txt)
    # print("Page content preview:")
    # idx = txt.find('Search Apartment #')
    # print(txt[idx:idx+1000])
    
    keywords = ["availability", "floor", "plans", "pricing"]
    candidates = set()

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        href = a["href"]

        if any(kw in text for kw in keywords):
            # Convert relative URL (e.g. "/floorplans") to absolute
            # candidates.append(href)
            full_url = urljoin(url, href)
            candidates.add(full_url)
    with open("candidates.txt", "w", encoding="utf-8") as f:
        f.write('\n'.join(candidates))
    # Take a screenshot for debugging
    # page.screenshot(path="debug_screenshot.png")
    # print(candidates)
    browser.close()
