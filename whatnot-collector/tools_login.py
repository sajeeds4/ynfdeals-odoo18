from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir="/home/cybertechna/.whatnot-profile",
        headless=False,
        channel="chrome",
    )
    page = context.new_page()
    page.goto("https://www.whatnot.com")
    input("Log in manually in the opened Chrome window, then press Enter here...")
    context.storage_state(path="/home/cybertechna/AethrixSystems_Portable/hjay9672-WN /whatnot-collector/storage_state.json")
    context.close()
