from playwright.sync_api import Page, expect


def test_home(page: Page, base_url: str):
    page.goto(base_url)
    expect(page.locator("h1")).to_contain_text("Noisebins")
