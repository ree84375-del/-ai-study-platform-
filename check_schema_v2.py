import os
from app import create_app, db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    try:
        inspector = inspect(db.engine)
        
        output = []
        for table_name in ['user', 'group']:
            output.append(f"Table: {table_name}")
            try:
                columns = inspector.get_columns(table_name)
                for column in columns:
                    output.append(f" - {column['name']} ({column['type']})")
            except Exception as e:
                output.append(f" Error inspecting {table_name}: {e}")
            output.append("")
            
        with open('schema_report.txt', 'w', encoding='utf-8') as f:
            f.write("\n".join(output))
        print("SUCCESS")
    except Exception as e:
        with open('schema_report.txt', 'w', encoding='utf-8') as f:
            f.write(f"FATAL ERROR: {e}")
        print("FAILED")
