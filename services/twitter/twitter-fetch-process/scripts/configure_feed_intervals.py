#!/usr/bin/env python3
"""
Generate randomized feed refresh schedule.

Usage:
    python configure_feed_intervals.py [options]

Examples:
    python configure_feed_intervals.py --randomize --output feed_schedule.json
    python configure_feed_intervals.py --min-interval 300 --max-interval 900
"""

import argparse
import json
import random
import sys
from typing import Dict, List


def generate_schedule(
    feed_count: int,
    min_interval: int,
    max_interval: int,
    randomize: bool
) -> Dict[str, any]:
    """
    Generate randomized feed refresh schedule.

    Args:
        feed_count: Number of feeds
        min_interval: Minimum refresh interval (seconds)
        max_interval: Maximum refresh interval (seconds)
        randomize: Whether to randomize intervals

    Returns:
        Schedule configuration dictionary
    """
    schedule = {
        "default_interval": (min_interval + max_interval) // 2,
        "min_interval": min_interval,
        "max_interval": max_interval,
        "feeds": []
    }

    for feed_id in range(1, feed_count + 1):
        if randomize:
            interval = random.randint(min_interval, max_interval)
        else:
            # Distribute evenly
            range_size = max_interval - min_interval
            step = range_size / max(1, feed_count - 1) if feed_count > 1 else 0
            interval = int(min_interval + step * (feed_id - 1))

        # Add some jitter (±10%)
        jitter = int(interval * 0.1)
        interval = random.randint(
            max(min_interval, interval - jitter),
            min(max_interval, interval + jitter)
        )

        schedule["feeds"].append({
            "feed_id": feed_id,
            "interval_seconds": interval,
            "interval_minutes": round(interval / 60, 1)
        })

    # Sort by interval
    schedule["feeds"].sort(key=lambda x: x["interval_seconds"])

    return schedule


def analyze_schedule(schedule: Dict[str, any]) -> Dict[str, any]:
    """
    Analyze schedule for load distribution.

    Args:
        schedule: Schedule configuration

    Returns:
        Analysis results
    """
    intervals = [feed["interval_seconds"] for feed in schedule["feeds"]]

    return {
        "total_feeds": len(intervals),
        "avg_interval": sum(intervals) / len(intervals) if intervals else 0,
        "min_interval": min(intervals) if intervals else 0,
        "max_interval": max(intervals) if intervals else 0,
        "estimated_requests_per_hour": sum(3600 / interval for interval in intervals) if intervals else 0
    }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate randomized feed refresh schedule"
    )
    parser.add_argument(
        '--feed-count',
        type=int,
        default=100,
        help="Number of feeds (default: 100)"
    )
    parser.add_argument(
        '--min-interval',
        type=int,
        default=300,
        help="Minimum refresh interval in seconds (default: 300 = 5 min)"
    )
    parser.add_argument(
        '--max-interval',
        type=int,
        default=1800,
        help="Maximum refresh interval in seconds (default: 1800 = 30 min)"
    )
    parser.add_argument(
        '--randomize',
        action='store_true',
        help="Randomize intervals (otherwise distribute evenly)"
    )
    parser.add_argument(
        '--output',
        default='feed_schedule.json',
        help="Output file path (default: feed_schedule.json)"
    )
    parser.add_argument(
        '--analyze',
        action='store_true',
        help="Print analysis of schedule"
    )

    args = parser.parse_args()

    # Validate intervals
    if args.min_interval <= 0:
        print("Error: min-interval must be positive", file=sys.stderr)
        sys.exit(1)

    if args.max_interval < args.min_interval:
        print("Error: max-interval must be >= min-interval", file=sys.stderr)
        sys.exit(1)

    # Generate schedule
    print(f"Generating schedule for {args.feed_count} feeds...")
    print(f"Interval range: {args.min_interval}s - {args.max_interval}s "
          f"({args.min_interval//60}min - {args.max_interval//60}min)")

    schedule = generate_schedule(
        feed_count=args.feed_count,
        min_interval=args.min_interval,
        max_interval=args.max_interval,
        randomize=args.randomize
    )

    # Analyze
    analysis = analyze_schedule(schedule)

    print(f"\nSchedule Analysis:")
    print(f"  Total feeds: {analysis['total_feeds']}")
    print(f"  Avg interval: {analysis['avg_interval']:.1f}s ({analysis['avg_interval']/60:.1f}min)")
    print(f"  Min interval: {analysis['min_interval']}s ({analysis['min_interval']/60:.1f}min)")
    print(f"  Max interval: {analysis['max_interval']}s ({analysis['max_interval']/60:.1f}min)")
    print(f"  Est. requests/hour: {analysis['estimated_requests_per_hour']:.1f}")

    # Save to file
    try:
        with open(args.output, 'w') as f:
            json.dump(schedule, f, indent=2)
        print(f"\n✓ Schedule saved to: {args.output}")
    except Exception as e:
        print(f"Error writing schedule: {e}", file=sys.stderr)
        sys.exit(1)

    # Print detailed analysis if requested
    if args.analyze:
        print(f"\nDetailed Schedule (first 10 feeds):")
        for feed in schedule["feeds"][:10]:
            print(f"  Feed {feed['feed_id']:3d}: {feed['interval_seconds']:4d}s ({feed['interval_minutes']:5.1f}min)")

        if len(schedule["feeds"]) > 10:
            print(f"  ... and {len(schedule['feeds']) - 10} more")


if __name__ == '__main__':
    main()
