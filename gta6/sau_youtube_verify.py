"""Read YouTube Studio receipts after the upstream CLI; never submit an upload."""
import asyncio
import re
from pathlib import Path
from patchright.async_api import async_playwright, expect

CHANNEL = 'UCdL4ljG4SqfEA8qk5yd6v5w'

async def _receipts(account_file, title):
    found = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True)
        try:
            context = await browser.new_context(storage_state=str(account_file),
                user_agent=f'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{browser.version} Safari/537.36')
            page = await context.new_page()
            for kind in ('short', 'upload'):
                prefix = f'https://studio.youtube.com/channel/{CHANNEL}/videos/{kind}'
                await page.goto(prefix, wait_until='domcontentloaded')
                await expect(page.locator('ytcp-video-row').first).to_be_visible(timeout=45000)
                if not page.url.startswith(prefix):
                    raise RuntimeError('YouTube verification left the exact channel')
                rows = page.locator('ytcp-video-row').filter(has=page.get_by_role('link', name=title, exact=True))
                for row in await rows.all():
                    link = await row.get_by_role('link', name=title, exact=True).get_attribute('href')
                    match = re.fullmatch(r'/video/([A-Za-z0-9_-]{11})/edit', link or '')
                    lines = (await row.inner_text()).splitlines()
                    visibility = next((v.lower() for v in ('Private', 'Public', 'Unlisted') if v in lines), None)
                    if match and visibility and 'Draft' not in lines:
                        found[match.group(1)] = {'status':'published','video_id':match.group(1),
                            'url':'https://www.youtube.com/watch?v='+match.group(1),
                            'verified_visibility':visibility,'channel_id':CHANNEL,'uploader':'sau CLI'}
            return found
        finally:
            await browser.close()

def receipts(account_file, title):
    return asyncio.run(_receipts(Path(account_file), title))
