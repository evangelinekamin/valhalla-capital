# extract_data.py
"""Stage 4: Extract structured financial data from newsletters using AI."""
import json
import logging
import re

from bs4 import BeautifulSoup

from db_schema import init_db
from model_client import create_model_client
from utils import retry_with_backoff, CostTracker
import discord_notifier

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are analyzing a financial newsletter for a quantitative trading system.

NEWSLETTER: {subject}
FROM: {sender}
DATE: {date}

--- CONTENT ---
{text_content}

{image_context}

Extract structured data as JSON:

{{
    "summary": "2-3 sentence summary of main points",

    "ticker_picks": [
        {{
            "ticker": "SYMBOL",
            "action": "new_pick|update|close|trim|add",
            "direction": "long|short",
            "sentiment": "bullish|bearish|neutral",
            "target_price": null or number,
            "stop_loss": null or number,
            "position_size": "percentage or description if mentioned",
            "timeframe": "short-term|medium-term|long-term or specific",
            "thesis": "1-2 sentence core reasoning",
            "catalysts": ["upcoming events or triggers"],
            "risks": ["key risks mentioned"],
            "confidence": "high|medium|low based on author's tone"
        }}
    ],

    "market_views": {{
        "overall_sentiment": "bullish|bearish|neutral|mixed",
        "sector_views": {{"sector": "sentiment"}},
        "macro_factors": ["key macro themes discussed"],
        "risk_factors": ["broad market risks mentioned"]
    }},

    "data_points": [
        {{
            "metric": "name",
            "value": "value with units",
            "ticker": "if specific to a stock",
            "context": "why it matters"
        }}
    ],

    "updates_to_previous": [
        {{
            "ticker": "SYMBOL",
            "original_thesis": "brief reminder if mentioned",
            "update": "what changed",
            "new_action": "hold|trim|add|close"
        }}
    ],

    "key_quotes": ["Notable direct quotes that capture conviction or insight"],

    "actionable_signals": [
        {{
            "signal": "description",
            "urgency": "immediate|this_week|monitor",
            "tickers_affected": ["LIST"]
        }}
    ]
}}

CRITICAL JSON FORMATTING RULES:
- Return ONLY valid, parseable JSON - no markdown, no code blocks, no explanations
- All string values MUST be properly escaped (use \\" for quotes inside strings)
- All arrays must have trailing commas between elements (not after last element)
- All object properties must have commas between them (not after last property)
- Use null (not "null" string) for missing numeric values
- Use [] for empty arrays, not null
- Use {{}} for empty objects, not null
- Double-check that all braces {{ }} and brackets [ ] are properly closed
- If a field has no relevant data, use null or empty array/object

Important:
- Extract ONLY information explicitly stated, don't infer
- Be precise with numbers - include currency/percentages as written
- Note when author is updating a previous pick vs. new recommendation
- Capture confidence level based on language (e.g., "I'm very confident" = high)

Return ONLY the JSON object, nothing else."""


@retry_with_backoff(max_retries=3, base_delay=2, exceptions=(Exception,))
def call_extraction_api(client, prompt, max_tokens=4096):
    """Call the model through the abstraction layer with retry logic."""
    return client.generate_text(prompt, max_tokens=max_tokens)


def extract_newsletter_content(conn, batch_size=10, model=None, backend="anthropic", **client_kwargs):
    """Extract structured data from unprocessed newsletters.

    Args:
        conn: SQLite database connection
        batch_size: Number of emails to process per batch
        model: Model name (uses config/backend default if None)
        backend: Model backend ("anthropic", "ollama", "llamacpp")
        **client_kwargs: Additional args passed to create_model_client

    Returns:
        CostTracker with this batch's costs
    """
    cost_tracker = CostTracker(conn)
    client = create_model_client(backend=backend, model=model, **client_kwargs)

    emails = conn.execute('''
        SELECT e.id, e.subject, e.sender, e.date, e.html
        FROM emails e
        WHERE e.id NOT IN (SELECT DISTINCT email_id FROM extracted_data WHERE email_id IS NOT NULL)
        LIMIT ?
    ''', (batch_size,)).fetchall()

    for email_id, subject, sender, date, html in emails:
        # Get vision outputs for this email's images
        image_descriptions = conn.execute('''
            SELECT local_path, vision_output FROM images
            WHERE email_id = ? AND vision_output IS NOT NULL
        ''', (email_id,)).fetchall()

        # Parse HTML to extract text
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'meta', 'link']):
            tag.decompose()

        text_content = soup.get_text(separator='\n', strip=True)
        text_content = re.sub(r'\n{3,}', '\n\n', text_content)

        # Build image context from vision outputs
        image_context = ""
        if image_descriptions:
            image_context = "--- IMAGE ANALYSIS ---\n"
            for path, description in image_descriptions:
                image_context += f"\n[{path}]\n{description}\n"

        prompt = EXTRACTION_PROMPT.format(
            subject=subject,
            sender=sender,
            date=date,
            text_content=text_content[:12000],
            image_context=image_context[:4000],
        )

        try:
            response = call_extraction_api(client, prompt)

            cost = cost_tracker.log_call(
                response.model or model or "unknown",
                response.input_tokens,
                response.output_tokens,
                purpose='extraction',
            )

            output = response.text

            # Parse and validate JSON with multiple fallback strategies
            parsed = None
            parse_error = None

            # Strategy 1: Direct parse
            try:
                parsed = json.loads(output)
            except json.JSONDecodeError as e:
                parse_error = e
                logger.debug(f"Direct JSON parse failed for {email_id}: {e}")

                # Strategy 2: Extract JSON from markdown code blocks
                code_block_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', output)
                if code_block_match:
                    try:
                        parsed = json.loads(code_block_match.group(1))
                        logger.debug(f"Successfully extracted JSON from code block for {email_id}")
                    except json.JSONDecodeError as e2:
                        logger.debug(f"Code block JSON parse failed for {email_id}: {e2}")

                # Strategy 3: Find JSON object with non-greedy matching
                if parsed is None:
                    # Try to find the first complete JSON object
                    json_matches = re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', output)
                    for match in json_matches:
                        try:
                            parsed = json.loads(match.group())
                            logger.debug(f"Successfully extracted JSON with non-greedy match for {email_id}")
                            break
                        except json.JSONDecodeError:
                            continue

                # Strategy 4: Greedy extraction (last resort)
                if parsed is None:
                    json_match = re.search(r'\{[\s\S]*\}', output)
                    if json_match:
                        try:
                            parsed = json.loads(json_match.group())
                            logger.debug(f"Successfully extracted JSON with greedy match for {email_id}")
                        except json.JSONDecodeError as e3:
                            # Log the malformed JSON for debugging
                            malformed_json = json_match.group()[:500]  # First 500 chars
                            logger.error(f"Malformed JSON for {email_id} at {e3.msg} (line {e3.lineno}, col {e3.colno}): {malformed_json}...")
                            parse_error = e3

            # If all strategies failed, raise an error
            if parsed is None:
                error_msg = f"Could not extract valid JSON from response. Last error: {parse_error}"
                logger.error(f"All JSON parsing strategies failed for {email_id}: {error_msg}")
                # Save the raw response for debugging
                with open(f'failed_extraction_{email_id}.txt', 'w') as f:
                    f.write(f"Email ID: {email_id}\n")
                    f.write(f"Subject: {subject}\n")
                    f.write(f"Error: {parse_error}\n\n")
                    f.write("Raw Response:\n")
                    f.write(output)
                raise ValueError(error_msg)

            # Store main extraction
            conn.execute(
                "INSERT INTO extracted_data (email_id, data_type, content) VALUES (?, ?, ?)",
                (email_id, 'structured', json.dumps(parsed))
            )

            # Store ticker picks in dedicated table for easy querying
            for pick in parsed.get('ticker_picks', []):
                if pick.get('ticker'):
                    conn.execute('''
                        INSERT INTO ticker_updates
                        (email_id, ticker, action, sentiment, target_price, stop_loss, thesis, confidence)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        email_id,
                        pick['ticker'],
                        pick.get('action'),
                        pick.get('sentiment'),
                        pick.get('target_price'),
                        pick.get('stop_loss'),
                        pick.get('thesis'),
                        pick.get('confidence'),
                    ))

            # Also store updates to previous picks
            for update in parsed.get('updates_to_previous', []):
                if update.get('ticker'):
                    conn.execute('''
                        INSERT INTO ticker_updates
                        (email_id, ticker, action, thesis)
                        VALUES (?, ?, ?, ?)
                    ''', (
                        email_id,
                        update['ticker'],
                        update.get('new_action', 'update'),
                        update.get('update'),
                    ))

            conn.commit()
            logger.info(f"Extracted: {subject[:50]}... (${cost:.4f})")

        except Exception as e:
            logger.error(f"Failed {email_id}: {e}")
            # Notify Discord for extraction errors
            discord_notifier.notify_error(
                e,
                stage="extraction",
                context={"email_id": email_id, "subject": subject[:100]},
                severity="error"
            )
            # Don't re-raise, continue with next email
            conn.rollback()

    return cost_tracker


def export_to_json(conn, output_path='newsletter_data.json'):
    """Export all extracted data to a JSON file."""
    rows = conn.execute('''
        SELECT e.id, e.subject, e.sender, e.date, ed.content
        FROM emails e
        JOIN extracted_data ed ON e.id = ed.email_id
        ORDER BY e.date DESC
    ''').fetchall()

    output = []
    for email_id, subject, sender, date, content in rows:
        try:
            data = json.loads(content)
            data['_meta'] = {
                'email_id': email_id,
                'subject': subject,
                'sender': sender,
                'date': date,
            }
            output.append(data)
        except json.JSONDecodeError:
            continue

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    logger.info(f"Exported {len(output)} newsletters to {output_path}")


def export_ticker_history(conn, output_path='ticker_history.json'):
    """Export ticker-centric view of all picks and updates."""
    rows = conn.execute('''
        SELECT
            t.ticker, t.action, t.sentiment, t.target_price,
            t.stop_loss, t.thesis, t.confidence,
            e.date, e.subject, e.sender
        FROM ticker_updates t
        JOIN emails e ON t.email_id = e.id
        ORDER BY t.ticker, e.date
    ''').fetchall()

    tickers = {}
    for row in rows:
        ticker = row[0]
        if ticker not in tickers:
            tickers[ticker] = []

        tickers[ticker].append({
            'action': row[1],
            'sentiment': row[2],
            'target_price': row[3],
            'stop_loss': row[4],
            'thesis': row[5],
            'confidence': row[6],
            'date': row[7],
            'source': row[8],
            'author': row[9],
        })

    with open(output_path, 'w') as f:
        json.dump(tickers, f, indent=2)

    logger.info(f"Exported history for {len(tickers)} tickers to {output_path}")


if __name__ == '__main__':
    from config import load_config

    cfg = load_config()
    conn = init_db(cfg.database_path)
    try:
        tracker = extract_newsletter_content(
            conn,
            batch_size=cfg.pipeline.batch_size,
            model=cfg.model.extraction_model or cfg.model.model,
            backend=cfg.model.backend,
            **cfg.model.client_kwargs(),
        )
        export_to_json(conn, cfg.output.newsletter_data)
        export_ticker_history(conn, cfg.output.ticker_history)
        tracker.print_summary()
    finally:
        conn.close()
