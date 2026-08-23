import os
from dotenv import load_dotenv
load_dotenv()
from app import app
from services.claude import refine_prompt
with app.app_context():
    print(refine_prompt('a dog walking'))
