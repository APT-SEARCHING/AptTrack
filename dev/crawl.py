from playwright.sync_api import sync_playwright
import time
from bs4 import BeautifulSoup

# url = "https://prometheusapartments.com/ca/santa-clara-apartments/the-benton#pricingAndFloorPlanBox"

url = 'https://www.irvinecompanyapartments.com/locations/northern-california/santa-clara/santa-clara-square/availability.html#floor-plan-list'

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
    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(txt)
    print("Page content preview:")
    idx = txt.find('Search Apartment #')
    print(txt[idx:idx+1000])
    
    # # Look for price information
    # price_div = soup.select_one('.fapt-fp-list-item__column.fapt-fp-list-item__column--price')
    # if price_div:
    #     price = price_div.get_text(strip=True)
    #     print("Price:", price)
    # else:
    #     print("Price information not found")
    
    # Take a screenshot for debugging
    # page.screenshot(path="debug_screenshot.png")
    
    browser.close()
