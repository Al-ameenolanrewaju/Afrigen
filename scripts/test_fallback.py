import os
from app import app
from services.provider_manager import provider_manager
from models import db, ProviderHealth, ProviderLog

def test_fallback():
    with app.app_context():
        db.create_all()
        print("--- Testing Normal Routing ---")
        try:
            res = provider_manager.generate_text(
                "Blog Writing", 
                [{"role": "user", "content": "Write a 5 word sentence about Africa."}]
            )
            print("Response:", res)
        except Exception as e:
            print("Error:", e)
            
        print("\n--- Testing Fallback (Simulating Groq Failure) ---")
        # Sabotage Groq
        original_key = os.environ.get('GROQ_API_KEY')
        os.environ['GROQ_API_KEY'] = 'fake_key'
        
        # We need to manually set the adapter's client to throw an error
        # Re-initialize the adapter to pick up the bad key
        from services.provider_manager import GroqAdapter
        provider_manager.adapters['Groq'] = GroqAdapter()
        
        try:
            # Task mapped to Groq
            res = provider_manager.generate_text(
                "Prompt Refinement",
                [{"role": "user", "content": "Say 'hello' in one word."}]
            )
            print("Response after fallback:", res)
        except Exception as e:
            print("Error after fallback:", e)
            
        print("\n--- Verifying Health DB ---")
        healths = ProviderHealth.query.all()
        for h in healths:
            print(f"{h.provider_name}: {h.status} (Success: {h.success_count}, Fails: {h.failure_count})")
            
        print("\n--- Verifying Log DB ---")
        logs = ProviderLog.query.order_by(ProviderLog.id.desc()).limit(2).all()
        for log in logs:
            print(f"Task: {log.task_type}, Provider: {log.provider_used}, Fallback: {log.fallback_triggered}, Error: {log.error_message}")
            
if __name__ == '__main__':
    test_fallback()
