from models import db, ProviderHealth
from datetime import datetime, timezone

class ProviderHealthService:
    @staticmethod
    def record_success(provider: str, latency_ms: int = 0):
        health = ProviderHealth.query.filter_by(provider=provider).first()
        if not health:
            health = ProviderHealth(provider=provider)
            db.session.add(health)
            
        health.success_count += 1
        health.status = "healthy"
        
        # Simple moving average for latency
        if health.avg_latency_ms == 0:
            health.avg_latency_ms = latency_ms
        else:
            health.avg_latency_ms = int((health.avg_latency_ms * 0.9) + (latency_ms * 0.1))
            
        db.session.commit()

    @staticmethod
    def record_failure(provider: str, error_msg: str):
        health = ProviderHealth.query.filter_by(provider=provider).first()
        if not health:
            health = ProviderHealth(provider=provider)
            db.session.add(health)
            
        health.failure_count += 1
        health.last_error = error_msg
        health.last_error_at = datetime.now(timezone.utc)
        
        # Very naive status determination
        total = health.success_count + health.failure_count
        if total > 5 and (health.failure_count / total) > 0.5:
            health.status = "degraded"
            
        db.session.commit()
        
    @staticmethod
    def is_provider_healthy(provider: str) -> bool:
        health = ProviderHealth.query.filter_by(provider=provider).first()
        if not health:
            return True # Assume healthy if no records
        return health.status != "down"
