import json
from pathlib import Path
from typing import List, Dict
import sys

sys.path.insert(0, str(Path(__file__).parent))
from alert_manager import AlertManager

class OverseerNewsClient:
    def __init__(self, alerts_path=None):
        if alerts_path is None:
            alerts_path = Path(__file__).parent.parent / "alerts" / "critical_alerts.json"
        self.alerts_path = Path(alerts_path)
    
    def check_critical_alerts(self) -> List[Dict]:
        try:
            with open(self.alerts_path, 'r') as f:
                alerts = json.load(f)
            
            unacknowledged = [a for a in alerts if not a.get('acknowledged', False)]
            return unacknowledged
        except FileNotFoundError:
            return []
    
    def acknowledge_alert(self, alert_id: int):
        alert_manager = AlertManager()
        alert_manager.acknowledge_alert(alert_id)
    
    def acknowledge_all_alerts(self):
        alert_manager = AlertManager()
        alert_manager.acknowledge_all()
    
    def get_alert_summary(self) -> str:
        alerts = self.check_critical_alerts()
        
        if not alerts:
            return "No critical alerts."
        
        summary = f"🚨 {len(alerts)} CRITICAL ALERT(S):\n\n"
        for alert in alerts:
            summary += f"[{alert['timestamp']}]\n"
            summary += f"  {alert['headline']}\n"
            summary += f"  {alert['summary'][:200]}...\n"
            summary += f"  Source: {alert['source']}\n"
            summary += f"  URL: {alert['url']}\n\n"
        
        return summary

if __name__ == "__main__":
    client = OverseerNewsClient()
    print(client.get_alert_summary())
