from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text('ALTER TABLE users ADD COLUMN country VARCHAR(100) NULL'))
        conn.execute(text("ALTER TABLE users ADD COLUMN signup_source VARCHAR(100) NULL DEFAULT 'direct'"))
        conn.commit()
    print('Columns added!')