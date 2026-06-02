from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text(
            'ALTER TABLE generations ADD COLUMN IF NOT EXISTS wants_voiceover BOOLEAN DEFAULT FALSE'
        ))
        conn.commit()
    print('Columns added!')
