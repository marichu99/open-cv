from playwright.async_api import Page
from playwright.sync_api import Locator, sync_playwright
import time
import os
from bs4 import BeautifulSoup


BASE_URL = "https://forms.iebc.or.ke"


def scrape_iebc() -> None:
    url = f"{BASE_URL}/index.php?r=results%2Fforms"
    os.makedirs("counties", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=['--start-maximized']
        )
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        page.goto(url, timeout=600000)
        time.sleep(3)

        # Count clickable county rows
        rows = page.locator("tr.crud-datatable[style*='cursor: pointer']")
        count = rows.count()
        print(f"Found {count} clickable county rows.")

        for i in range(count):
            get_in_county(page, rows, count, i)

            # Return to main page via KENYA breadcrumb link
            page.locator("//a[normalize-space()='KENYA']").click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            # Re-acquire rows after navigation back
            rows = page.locator("tr.crud-datatable[style*='cursor: pointer']")

        browser.close()
        print("Done.")

def get_in_county(page: Page, rows: Locator, count: int, i: int) -> None:
    row = rows.nth(i)
    county_name = row.locator("td[data-col-seq='0']").inner_text().strip()
    county_id = row.get_attribute("id")
    print(f"[{i+1}/{count}] Clicking county {county_name} (id={county_id}) ...")

    row.click()
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    
    con_rows = page.locator("tr.crud-datatable[style*='cursor: pointer']")
    con_count = con_rows.count()
    print(f"  Found {con_count} constituencies in {county_name}.")

    for j in range(con_count):
        get_in_constituency(page, con_rows, con_count, j, county_name)

        # Return to county page via county breadcrumb (match by id to avoid name collisions)
        page.locator(f"//a[contains(@href, 'id={county_id}')]").click()
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Re-acquire constituency rows after navigating back
        con_rows = page.locator("tr.crud-datatable[style*='cursor: pointer']")


def get_in_constituency(page: Page, rows: Locator, count: int, i: int, county_name: str) -> None:
    row = rows.nth(i)
    con_name = row.locator("td[data-col-seq='0']").inner_text().strip()
    con_id = row.get_attribute("id")
    print(f"    [{i+1}/{count}] Clicking constituency {con_name} (id={con_id}) ...")

    row.click()
    page.wait_for_load_state("networkidle")
    time.sleep(1)

    ward_rows = page.locator("tr.crud-datatable[style*='cursor: pointer']")
    ward_count = ward_rows.count()
    print(f"      Found {ward_count} wards in {con_name}.")

    for k in range(ward_count):
        get_in_ward(page, ward_rows, ward_count, k, county_name, con_name)

        # Return to constituency page via constituency breadcrumb (match by id to avoid name collisions)
        page.locator(f"//a[contains(@href, 'id={con_id}')]").click()
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Re-acquire ward rows after navigating back
        ward_rows = page.locator("tr.crud-datatable[style*='cursor: pointer']")


def get_in_ward(page: Page, rows: Locator, count: int, i: int, county_name: str, con_name: str) -> None:
    row = rows.nth(i)
    ward_name = row.locator("td[data-col-seq='0']").inner_text().strip()
    ward_id = row.get_attribute("id")
    print(f"        [{i+1}/{count}] Clicking ward {ward_name} (id={ward_id}) ...")

    row.click()
    page.wait_for_load_state("networkidle")
    time.sleep(1)

    # Click each polling station within this ward
    os.makedirs("polling_stations", exist_ok=True)
    ps_rows = page.locator("tr.crud-datatable[style*='cursor: pointer']")
    ps_count = ps_rows.count()
    print(f"          Found {ps_count} polling stations in {ward_name}.")

    for m in range(ps_count):
        get_in_polling_station(page, ps_rows, ps_count, m, county_name, con_name, ward_name)

        # Return to ward page via ward breadcrumb (match by id to avoid name collisions)
        page.locator(f"//a[contains(@href, 'id={ward_id}')]").click()
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Re-acquire polling station rows after navigating back
        ps_rows = page.locator("tr.crud-datatable[style*='cursor: pointer']")


def get_in_polling_station(page: Page, rows: Locator, count: int, i: int, county_name: str, con_name: str, ward_name: str) -> None:
    row = rows.nth(i)
    ps_name = row.locator("td[data-col-seq='0']").inner_text().strip()
    ps_id = row.get_attribute("id")
    print(f"            [{i+1}/{count}] Clicking polling station {ps_name} (id={ps_id}) ...")

    row.click()
    page.wait_for_load_state("networkidle")
    time.sleep(1)

    # Download all form documents via cloud-download buttons
    download_btns = page.locator("//i[@class='fa fa-cloud-download text-green']")
    btn_count = download_btns.count()
    if btn_count == 0:
        print(f"            No download button found for {ps_name}, skipping.")
        return

    dest_dir = os.path.join(
        "/home/mabera/personal/FORM34A",
        county_name, con_name, ward_name, ps_name
    )
    os.makedirs(dest_dir, exist_ok=True)

    for n in range(btn_count):
        with page.expect_download() as download_info:
            download_btns.nth(n).click()
        download = download_info.value
        dest_path = os.path.join(dest_dir, download.suggested_filename)
        download.save_as(dest_path)
        print(f"            Downloaded [{n+1}/{btn_count}] -> {dest_path}")

if __name__ == "__main__":
    scrape_iebc()
