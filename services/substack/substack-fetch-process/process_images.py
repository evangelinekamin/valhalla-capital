# process_images.py
"""Stage 2: Extract and download images from newsletter HTML."""
import hashlib
import logging
import re

import requests
from pathlib import Path
from PIL import Image

from db_schema import init_db

logger = logging.getLogger(__name__)

# Substack UI patterns to skip
SKIP_URL_PATTERNS = [
    r'substackcdn\.com.*/(buttons|icons)/',
    r'substack\.com/img/',
    r'substackcdn\.com.*/badge',
    r'substackcdn\.com.*/logo',
    r'substackcdn\.com.*/avatar',
    r'substackcdn\.com.*/favicon',
    r'/emoji/',
    r'/social[-_]?(icon|logo)',
    r'(twitter|facebook|linkedin|instagram|youtube).*\.(png|svg)',
    r'(share|like|comment|subscribe).*\.(png|svg|gif)',
]

# Minimum dimensions (pixels) - smaller is likely an icon
MIN_WIDTH = 100
MIN_HEIGHT = 100

# Minimum file size (bytes)
MIN_FILE_SIZE = 5000  # 5KB


def should_skip_url(url):
    """Check if URL matches known UI element patterns."""
    url_lower = url.lower()
    for pattern in SKIP_URL_PATTERNS:
        if re.search(pattern, url_lower):
            return True
    return False


def image_hash(image_bytes):
    """Generate hash of image content for deduplication."""
    return hashlib.md5(image_bytes).hexdigest()


def is_too_small(filepath):
    """Check if image is too small to be useful content."""
    try:
        if filepath.stat().st_size < MIN_FILE_SIZE:
            return True

        with Image.open(filepath) as img:
            width, height = img.size
            if width < MIN_WIDTH or height < MIN_HEIGHT:
                return True
    except Exception:
        pass

    return False


def extract_and_download_images(conn, image_dir='images', timeout=10):
    """Download and deduplicate images from newsletter HTML.

    Args:
        conn: SQLite database connection
        image_dir: Directory to save downloaded images
        timeout: HTTP request timeout in seconds
    """
    Path(image_dir).mkdir(exist_ok=True)

    # Track hashes we've seen (maps hash -> image record id)
    hash_to_id = {}

    # Load existing hashes from DB
    existing = conn.execute('''
        SELECT id, image_hash FROM images WHERE image_hash IS NOT NULL
    ''').fetchall()
    for img_id, img_hash in existing:
        hash_to_id[img_hash] = img_id

    # Find emails with unprocessed images
    emails = conn.execute('''
        SELECT id, html FROM emails
        WHERE id NOT IN (SELECT DISTINCT email_id FROM images WHERE email_id IS NOT NULL)
    ''').fetchall()

    stats = {'downloaded': 0, 'skipped_url': 0, 'skipped_size': 0, 'skipped_duplicate': 0}

    for email_id, html in emails:
        urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)

        for i, url in enumerate(urls):
            if not url.startswith('http'):
                continue

            # Skip known UI patterns
            if should_skip_url(url):
                stats['skipped_url'] += 1
                continue

            try:
                resp = requests.get(url, timeout=timeout)
                resp.raise_for_status()

                content = resp.content
                img_hash = image_hash(content)

                # Check for duplicate content
                if img_hash in hash_to_id:
                    conn.execute('''
                        INSERT INTO images (email_id, url, image_hash, duplicate_of)
                        VALUES (?, ?, ?, ?)
                    ''', (email_id, url, img_hash, hash_to_id[img_hash]))
                    stats['skipped_duplicate'] += 1
                    continue

                # Determine file extension from Content-Type with whitelist
                ext = resp.headers.get('content-type', 'image/png').split('/')[-1].split(';')[0]
                if ext not in ('png', 'jpg', 'jpeg', 'gif', 'webp'):
                    ext = 'png'

                filename = f"{email_id}_{i}.{ext}"
                filepath = Path(image_dir) / filename
                filepath.write_bytes(content)

                # Check size
                if is_too_small(filepath):
                    filepath.unlink()
                    stats['skipped_size'] += 1
                    continue

                # Insert record
                conn.execute('''
                    INSERT INTO images (email_id, url, local_path, image_hash)
                    VALUES (?, ?, ?, ?)
                ''', (email_id, url, str(filepath), img_hash))

                hash_to_id[img_hash] = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                stats['downloaded'] += 1

            except Exception as e:
                logger.warning(f"Failed: {url[:50]}... - {e}")

        conn.commit()

    logger.info(f"Downloaded: {stats['downloaded']}")
    logger.info(f"Skipped (URL pattern): {stats['skipped_url']}")
    logger.info(f"Skipped (too small): {stats['skipped_size']}")
    logger.info(f"Skipped (duplicate): {stats['skipped_duplicate']}")


if __name__ == '__main__':
    from config import load_config

    cfg = load_config()
    conn = init_db(cfg.database_path)
    try:
        extract_and_download_images(conn, image_dir=cfg.images.directory, timeout=cfg.images.download_timeout)
    finally:
        conn.close()
