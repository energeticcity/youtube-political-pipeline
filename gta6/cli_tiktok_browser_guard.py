"""Invoke the upstream CLI, stopping before publish unless it selected Only you.

This guard is only for private integration tests, not scheduled publication.
"""
import sys
from tiktok_uploader import cli, upload

original_post = upload._post_video


def private_post(page):
    control = page.locator('[data-e2e="video_visibility_container"] button[role="combobox"]')
    if control.count() != 1 or control.inner_text().strip().lower() != 'only you':
        raise RuntimeError('Private test visibility was not confirmed; publication stopped')
    print('PRIVATE_PUBLICATION_GUARD_PASSED', flush=True)
    return original_post(page)


upload._post_video = private_post
sys.argv[0] = 'tiktok-uploader'
cli.main()
