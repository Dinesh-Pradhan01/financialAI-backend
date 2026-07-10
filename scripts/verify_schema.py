import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
insp = inspect(engine)

print("Tables:", insp.get_table_names())
print()

for table in ["users", "sessions"]:
    print(f"--- {table} columns ---")
    for c in insp.get_columns(table):
        print(f"  {c['name']:25s} {str(c['type']):20s} nullable={c['nullable']}")
    print()

engine.dispose()
