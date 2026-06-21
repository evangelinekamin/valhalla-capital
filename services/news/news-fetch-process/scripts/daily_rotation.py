#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from alert_manager import AlertManager

if __name__ == "__main__":
    manager = AlertManager()
    manager.archive_and_reset()
    print(f"✅ Daily rotation complete - {datetime.now()}")
