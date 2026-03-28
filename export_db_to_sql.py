import os
from app import create_app, db
from app.models import Question

def export_questions():
    app = create_app()
    with app.app_context():
        questions = Question.query.all()
        
        with open("import_questions.sql", "w", encoding="utf-8") as f:
            f.write("-- Vercel PostgreSQL Import Script for Questions\n")
            f.write("BEGIN;\n")
            count = 0
            for q in questions:
                # Escape single quotes in Postgres
                content = (q.content_text or '').replace("'", "''")
                opt_a = (q.option_a or '').replace("'", "''")
                opt_b = (q.option_b or '').replace("'", "''")
                opt_c = (q.option_c or '').replace("'", "''")
                opt_d = (q.option_d or '').replace("'", "''")
                ans = (q.correct_answer or '').replace("'", "''")
                exp = (q.explanation or '').replace("'", "''")
                subj = (q.subject or '').replace("'", "''")
                cat = (q.category or '').replace("'", "''")
                tags = (q.tags or '').replace("'", "''")
                
                sql = f"""INSERT INTO question (subject, category, content_text, option_a, option_b, option_c, option_d, correct_answer, explanation, tags, difficulty) 
VALUES ('{subj}', '{cat}', '{content}', '{opt_a}', '{opt_b}', '{opt_c}', '{opt_d}', '{ans}', '{exp}', '{tags}', {q.difficulty});\n"""
                f.write(sql)
                count += 1
                
            f.write("COMMIT;\n")
            print(f"Exported {count} questions to import_questions.sql")
            print("To import this into Vercel Postgres, go to Vercel Dashboard -> Storage -> run the query in 'Query' tab.")

if __name__ == '__main__':
    export_questions()
