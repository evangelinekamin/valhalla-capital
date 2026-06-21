# vision_process.py
"""Stage 3: Process images with vision models."""
import base64
import logging
from pathlib import Path

from model_client import create_model_client
from utils import CostTracker
import discord_notifier

logger = logging.getLogger(__name__)

VISION_PROMPT = """Analyze this image from a financial newsletter. Describe:
1. What type of visualization this is (chart, table, screenshot, etc.)
2. Key data points, numbers, and trends visible
3. Any ticker symbols, dates, or financial metrics shown
4. The main takeaway or insight the image conveys

Be precise with numbers and labels. If text is visible, transcribe it accurately."""


def process_unprocessed_images(conn, batch_size=10, model=None, backend="anthropic", **client_kwargs):
    """Process a batch of unprocessed images through the vision model.

    Args:
        conn: SQLite database connection
        batch_size: Number of images to process per batch
        model: Model name (uses config/backend default if None)
        backend: Model backend ("anthropic", "ollama", "llamacpp")
        **client_kwargs: Additional args passed to create_model_client (e.g. api_key, base_url)

    Returns:
        CostTracker with this batch's costs
    """
    cost_tracker = CostTracker(conn)
    client = create_model_client(backend=backend, model=model, **client_kwargs)

    images = conn.execute('''
        SELECT id, local_path FROM images
        WHERE vision_output IS NULL
          AND local_path IS NOT NULL
          AND duplicate_of IS NULL
        LIMIT ?
    ''', (batch_size,)).fetchall()

    for img_id, local_path in images:
        path = Path(local_path)
        if not path.exists():
            logger.warning(f"Image file missing: {local_path}")
            continue

        try:
            img_data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
            media_type = f"image/{path.suffix.lstrip('.')}"
            if media_type == "image/jpg":
                media_type = "image/jpeg"

            response = client.generate_vision(
                prompt=VISION_PROMPT,
                image_data=img_data,
                media_type=media_type,
                max_tokens=1024,
            )

            cost = cost_tracker.log_call(
                response.model or model or "unknown",
                response.input_tokens,
                response.output_tokens,
                purpose="vision",
            )

            # Update this image
            conn.execute(
                "UPDATE images SET vision_output = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (response.text, img_id),
            )

            # Propagate vision output to any duplicates of this image
            img_hash = conn.execute(
                "SELECT image_hash FROM images WHERE id = ?", (img_id,)
            ).fetchone()[0]
            if img_hash:
                conn.execute(
                    "UPDATE images SET vision_output = ?, processed_at = CURRENT_TIMESTAMP WHERE duplicate_of = ?",
                    (response.text, img_id),
                )

            conn.commit()
            logger.info(f"Processed {path.name} (${cost:.4f})")

        except Exception as e:
            logger.error(f"Failed {local_path}: {e}")
            # Notify Discord for vision processing errors
            discord_notifier.notify_error(
                e,
                stage="vision",
                context={"image_path": str(local_path), "image_id": img_id},
                severity="warning"
            )

    return cost_tracker


if __name__ == "__main__":
    from config import load_config
    from db_schema import init_db

    cfg = load_config()
    conn = init_db(cfg.database_path)
    try:
        tracker = process_unprocessed_images(
            conn,
            batch_size=cfg.pipeline.batch_size,
            model=cfg.model.vision_model or cfg.model.model,
            backend=cfg.model.backend,
            **cfg.model.client_kwargs(),
        )
        tracker.print_summary()
    finally:
        conn.close()
