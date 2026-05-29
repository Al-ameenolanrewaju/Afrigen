from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text('ALTER TABLE users ADD COLUMN monthly_videos_used INTEGER DEFAULT 0'))
        conn.execute(text('ALTER TABLE users ADD COLUMN last_video_reset DATE NULL'))
        conn.commit()
    print('Columns added!')