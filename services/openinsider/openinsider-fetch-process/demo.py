#!/usr/bin/env python3
"""Demo script showing both Phase 1 and Phase 2 functionality."""

from openinsider.database import OpenInsiderDB


def main():
    """Run comprehensive demo."""
    db = OpenInsiderDB()

    print("=" * 80)
    print("OpenInsider Scraper - Complete Demo")
    print("=" * 80)

    # Phase 1: Cluster Buys
    print("\n📊 PHASE 1: Cluster Buys (Aggregated Data)")
    print("-" * 80)

    recent = db.get_recent_clusters(limit=10)
    print(f"\nFound {len(recent)} recent cluster buys:\n")

    for i, cluster in enumerate(recent[:5], 1):
        print(f"{i}. {cluster['ticker']:8} - {cluster['company_name'][:40]:40}")
        value_str = f"${cluster['total_value']:>12,}" if cluster['total_value'] else "         N/A"
        print(f"   Insiders: {cluster['insider_count']:3} | "
              f"Value: {value_str} | "
              f"Date: {cluster['trade_date']}")

    # Phase 2: Individual Insider Details
    print("\n\n👤 PHASE 2: Individual Insider Details")
    print("-" * 80)

    # Show executives buying
    print("\n🎯 Executive Purchases (CEO, CFO, Officers):\n")
    execs = db.get_executive_transactions(days=90)
    print(f"Found {len(execs)} executive transactions\n")

    for i, txn in enumerate(execs[:10], 1):
        qty_str = f"{txn['qty']:>10,}" if txn['qty'] else "N/A"
        value_str = f"${txn['value']:>10,}" if txn['value'] else "N/A"
        print(f"{i:2}. {txn['ticker']:8} - {txn['insider_name'][:30]:30}")
        print(f"    {txn['insider_title'][:30]:30} | "
              f"Shares: {qty_str} | Value: {value_str}")

    # Show insider breakdown for specific ticker
    print("\n\n🔍 Detailed Breakdown for ALLY:")
    print("-" * 80)

    ally_txns = db.get_insider_transactions("ALLY", days=90)
    print(f"Found {len(ally_txns)} transactions\n")

    for txn in ally_txns:
        insider_type = f"[{txn['insider_type']}]"
        qty_str = f"{txn['qty']:>10,}" if txn['qty'] else "N/A"
        print(f"{txn['insider_name'][:35]:35} {insider_type:12} "
              f"{txn['trade_type']:15} {qty_str}")

    # Stats
    print("\n\n📈 Scrape Statistics:")
    print("-" * 80)

    stats = db.get_scrape_stats(limit=5)
    for stat in stats:
        print(f"{stat['scrape_timestamp'][:19]} | "
              f"{stat['scrape_type']:20} | "
              f"Found: {stat['records_found']:4} | "
              f"New: {stat['records_new']:4} | "
              f"Status: {stat['status']}")

    # Summary
    print("\n\n✅ Summary:")
    print("-" * 80)

    with db._get_connection() as conn:
        cluster_count = conn.execute("SELECT COUNT(*) FROM cluster_buys").fetchone()[0]
        insider_count = conn.execute("SELECT COUNT(*) FROM insider_transactions").fetchone()[0]
        exec_count = conn.execute(
            "SELECT COUNT(*) FROM insider_transactions WHERE insider_type = 'executive'"
        ).fetchone()[0]
        fund_count = conn.execute(
            "SELECT COUNT(*) FROM insider_transactions WHERE insider_type = 'fund'"
        ).fetchone()[0]

    print(f"Total cluster buys:       {cluster_count:6}")
    print(f"Total insider txns:       {insider_count:6}")
    print(f"  - Executives:           {exec_count:6}")
    print(f"  - Funds (10% owners):   {fund_count:6}")

    print("\n" + "=" * 80)
    print("✨ Both phases working perfectly!")
    print("=" * 80)


if __name__ == "__main__":
    main()
