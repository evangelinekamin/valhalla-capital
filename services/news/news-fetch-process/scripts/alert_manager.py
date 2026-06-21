import json
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict
import shutil

class AlertManager:
    def __init__(self, base_path=None):
        if base_path is None:
            base_path = Path(__file__).parent.parent / "alerts"
        self.base_path = Path(base_path)
        self.alerts_file = self.base_path / "critical_alerts.json"
        self.archive_dir = self.base_path / "archive"
        
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(exist_ok=True)
        self._init_todays_file()
    
    def _init_todays_file(self):
        if not self.alerts_file.exists():
            self._write_alerts([])
        else:
            alerts = self._read_alerts()
            if alerts and alerts[0].get('date') != str(date.today()):
                self.archive_and_reset()
    
    def _read_alerts(self) -> List[Dict]:
        try:
            with open(self.alerts_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    def _write_alerts(self, alerts: List[Dict]):
        temp_file = self.alerts_file.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            json.dump(alerts, f, indent=2, default=str)
        temp_file.replace(self.alerts_file)
    
    def add_critical_alert(self, alert: Dict):
        alerts = self._read_alerts()
        
        alert_entry = {
            'id': len(alerts) + 1,
            'date': str(date.today()),
            'timestamp': datetime.now().isoformat(),
            'headline': alert['headline'],
            'summary': alert['summary'],
            'full_text': alert.get('full_text', ''),
            'url': alert['url'],
            'source': alert['source'],
            'acknowledged': False
        }
        
        alerts.append(alert_entry)
        self._write_alerts(alerts)
        
        print(f"🚨 CRITICAL ALERT ADDED: {alert['headline']}")
        return alert_entry['id']
    
    def get_unacknowledged_alerts(self) -> List[Dict]:
        alerts = self._read_alerts()
        return [a for a in alerts if not a.get('acknowledged', False)]
    
    def acknowledge_alert(self, alert_id: int):
        alerts = self._read_alerts()
        for alert in alerts:
            if alert['id'] == alert_id:
                alert['acknowledged'] = True
                alert['acknowledged_at'] = datetime.now().isoformat()
        self._write_alerts(alerts)
    
    def acknowledge_all(self):
        alerts = self._read_alerts()
        for alert in alerts:
            if not alert.get('acknowledged', False):
                alert['acknowledged'] = True
                alert['acknowledged_at'] = datetime.now().isoformat()
        self._write_alerts(alerts)
    
    def archive_and_reset(self):
        if self.alerts_file.exists():
            alerts = self._read_alerts()
            if alerts:
                alert_date = alerts[0].get('date', str(date.today()))
                archive_file = self.archive_dir / f"{alert_date}.json"
                shutil.copy2(self.alerts_file, archive_file)
                print(f"📦 Archived {len(alerts)} alerts to {archive_file}")
        
        self._write_alerts([])
    
    def get_stats(self) -> Dict:
        alerts = self._read_alerts()
        unacknowledged = [a for a in alerts if not a.get('acknowledged', False)]
        
        return {
            'total_today': len(alerts),
            'unacknowledged': len(unacknowledged),
            'acknowledged': len(alerts) - len(unacknowledged),
            'latest_alert': alerts[-1] if alerts else None
        }
