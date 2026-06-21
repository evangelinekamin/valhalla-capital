#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent))
from alert_manager import AlertManager

def print_dashboard():
    manager = AlertManager()
    stats = manager.get_stats()
    alerts = manager.get_unacknowledged_alerts()
    
    print("\n" + "="*60)
    print("🚨 CRITICAL ALERTS DASHBOARD")
    print("="*60)
    print(f"Date: {date.today()}")
    print(f"Total Alerts Today: {stats['total_today']}")
    print(f"Unacknowledged: {stats['unacknowledged']}")
    print(f"Acknowledged: {stats['acknowledged']}")
    
    if alerts:
        print(f"\n⚠️  PENDING ALERTS:")
        for alert in alerts:
            print(f"\n  [{alert['timestamp']}]")
            print(f"  {alert['headline']}")
            print(f"  {alert['url']}")
    else:
        print("\n✅ No pending alerts")
    
    print("="*60 + "\n")

if __name__ == "__main__":
    print_dashboard()
