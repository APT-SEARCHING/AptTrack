from playwright.sync_api import sync_playwright
import time
from bs4 import BeautifulSoup


def clean_html_for_llm(raw_html):
    soup = BeautifulSoup(raw_html, "html.parser")
    
    # focus on <body>
    body = soup.body
    if not body:
        return ""
    
    # remove scripts and styles
    for tag in body(["script", "style", "noscript", "meta", "link"]):
        tag.decompose()
    
    # Optionally, replace long text blocks with placeholders
    # for el in body.find_all():
    #     if len(el.text) > 200:
    #         el.string = "[LONG_TEXT]"
    
    # convert back to string
    clean_html = str(body)
    return clean_html

def extract_clickables(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")

    # Elements we care about
    candidates = []

    # Buttons / links
    for tag in soup.find_all(["a", "button", "li", "span", "div"], recursive=True):
        text = tag.get_text(strip=True)
        attrs = " ".join([f'{k}="{v}"' for k,v in tag.attrs.items()])
        
        # keep if it looks clickable (role=tab, onclick, href, data-*, etc.)
        if (
            tag.has_attr("onclick")
            or tag.has_attr("href")
            or tag.has_attr("role") and "tab" in tag["role"]
            or any(k.startswith("data-") for k in tag.attrs.keys())
            or "click" in attrs.lower()
            or "floor" in text.lower()
            or "plan" in text.lower()
        ):
            candidates.append(f"<{tag.name} {attrs}>{text}</{tag.name}>")

    # Iframes
    for iframe in soup.find_all("iframe"):
        attrs = " ".join([f'{k}=\"{v}\"' for k,v in iframe.attrs.items()])
        candidates.append(f"<iframe {attrs}></iframe>")

    return "\n".join(candidates)

url = 'https://diridonwest.com/floorplans/'
url = 'https://www.rentmiro.com/floorplans'
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)  # Set to False to see what's happening
    page = browser.new_page()
    
    print("Navigating to the page...")
    page.goto(url)
    
    # Wait for any content to load and stabilize
    time.sleep(5)
    # Click the "Floor Plan" tab

    html_main = page.content()
    iframe_element = page.wait_for_selector("iframe")
    frame = iframe_element.content_frame()
    html_iframe = frame.content()
    # --- Parse both with BeautifulSoup ---
    soup_main = BeautifulSoup(html_main, 'html.parser')
    soup_iframe = BeautifulSoup(html_iframe, 'html.parser')

    # --- Combine the two bodies into one string ---
    combined_html = ""
    if soup_main.body:
        combined_html += str(soup_main.body)
    if soup_iframe.body:
        combined_html += str(soup_iframe.body)

    # --- Clean for LLM ---
    # clean_html = clean_html_for_llm(combined_html)

    clean_html = extract_clickables(combined_html)
    # html = page.content()
    soup = BeautifulSoup(clean_html, 'html.parser')
    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(clean_html)
    txt = soup.get_text(separator="\n", strip=True)
    with open("output_miro1.txt", "w", encoding="utf-8") as f:
        f.write(txt)

    soup = BeautifulSoup(combined_html, 'html.parser')
    with open("output_1.txt", "w", encoding="utf-8") as f:
        f.write(combined_html)
    txt = soup.get_text(separator="\n", strip=True)
    with open("output_miro2.txt", "w", encoding="utf-8") as f:
        f.write(txt)

    # page.click("a[data-jd-fp-selector='tab'][data-tab='listing']")
    # page.click("a[role='tab']:has-text('Floor Plans')")
    # page.wait_for_selector("[data-jd-fp-selector='floorplan-card']", timeout=60000)
    # Wait for iframe element to be attached
    # iframe_element = page.wait_for_selector("iframe")

    # # Get Frame object from element handle
    # frame = iframe_element.content_frame()

    # # Now you can work inside the iframe
    # html1 = frame.content()

    # # Wait for floor plan content to load (e.g. specific selector)
    # # time.sleep(5)
    # print("Getting page content...")
    # # html = iframe.locator("body").inner_html()

    # # floor_buttons = frame.query_selector_all("[data-floor]")
    # # print(len(floor_buttons))
    # # for btn in floor_buttons:
    # #     print(btn.inner_text())
    # # Save the HTML for debugging
    # # with open("output.txt", "w", encoding="utf-8") as f:
    # #     f.write(html)
    
    # # Parse with BeautifulSoup
    # soup = BeautifulSoup(html1, 'html.parser')
    # with open("output2.txt", "w", encoding="utf-8") as f:
    #     f.write(html+html1)
    # # Get text content (first 1000 chars)
    # txt = soup.get_text(separator="\n", strip=True)
    # with open("output_miro2.txt", "w", encoding="utf-8") as f:
    #     f.write(txt)
    # # print("Page content preview:")
    # idx = txt.find('Search Apartment #')

    
    browser.close()
