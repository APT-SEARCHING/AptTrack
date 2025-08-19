from playwright.sync_api import sync_playwright
import time
from bs4 import BeautifulSoup


url = 'https://www.equityapartments.com/san-francisco-bay/north-san-jose/vista-99-apartments##unit-availability-tile'

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
    txt = soup.get_text(separator="\n", strip=True)
    with open("output_vista_99.txt", "w", encoding="utf-8") as f:
        f.write(txt)
    print("Page content preview:")
    idx = txt.find('Search Apartment #')

    
    browser.close()
