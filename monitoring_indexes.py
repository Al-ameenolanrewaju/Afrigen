from sqlalchemy import Index

from models import CreditLedger, Generation, Payment, PaystackWebhookLog, ProviderLog


Index("ix_generations_status_created_at", Generation.status, Generation.created_at)
Index("ix_generations_created_at", Generation.created_at)
Index("ix_provider_logs_timestamp", ProviderLog.timestamp)
Index("ix_paystack_webhook_logs_created_at", PaystackWebhookLog.created_at)
Index("ix_payments_created_at", Payment.created_at)
Index("ix_credit_ledger_created_at_user_id", CreditLedger.created_at, CreditLedger.user_id)
