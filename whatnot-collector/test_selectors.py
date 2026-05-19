from playwright.sync_api import sync_playwright

def test_stream():
    url = "https://www.whatnot.com/live/1712da23-1217-45b6-b7dd-3f34e06647c3"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print(f"Joining stream: {url}")
        
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(10000)
        
        print("\n--- DOM Testing ---")
        # Try to find the chat container
        chat_containers = page.locator("div[class*='chat']").all()
        print(f"Found {len(chat_containers)} chat containers.")
        if chat_containers:
            print("Chat container HTML preview:")
            print(chat_containers[-1].inner_html()[:1000])
        else:
            print("No chat containers found. Dumping body snippet:")
            print(page.locator("body").inner_html()[:1000])
                
        winners = page.locator("[data-testid='show-winning-status']").all()
        print(f"Found {len(winners)} winner elements.")
        
        browser.close()

if __name__ == "__main__":
    test_stream()
