import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "grader.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # ให้ดึงข้อมูลแบบ dict ได้
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # ตาราง user
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
                   id       INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT NOT NULL UNIQUE,
                   password TEXT NOT NULL,
                   created at DATETIME DEFUALT CURRENT_TIMESTAMP
                   )
            """) # ตัว """ 3ตัวนี้เอาไว้ทำให้เขียนคำสั่ง sql ได้หลายบรรทัดในทีเดียว
    
    # ตาราง โจทย์
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS problems (
                   id           INTEGER PRIMARY KEY AUTOINCREMENT,
                   title        TEXT NOT NULL UNIQUE,
                   description  TEXT NOT NULL,
                   category     TEXT NOT NULL,
                   difficulty   TEXT NOT NULL DEFAULT 'easy'
                   )
            """)
    
    # ตาราง test case
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_cases (
                   id           INTEGER PRIMARY KEY AUTOINCREMENT,
                   problem_id   INTEGER NOT NULL,
                   input_data   TEXT NOT NULL,
                   expected     TEXT NOT NULL,
                   is_hidden    INTEGER NOT NULL DEFAULT 0,
                   FOREIGN KEY (problem_id) REFERENCES problems(id)
                   )
            """)
            
    # ตาราง submissions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
                   id           INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id      INTEGER NOT NULL,
                   problem_id   INTEGER NOT NULL,
                   code         TEXT NOT NULL,
                   status       TEXT NOT NULL,
                   submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                   FOREIGN KEY (user_id) REFERENCES users(id),
                   FOREIGN KEY (problem_id) REFERENCES problems(id)
                   )
            """)
    
    # ตาราง error_logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS error_logs (
                   id           INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id      INTEGER NOT NULL,
                   problem_id   INTEGER NOT NULL,
                   submission_id    INTEGER NOT NULL,
                   error_type       TEXT NOT NULL,
                   error_message    TEXT NOT NULL,
                   error_line    INTEGER,
                   logged_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
                   FOREIGN KEY (user_id) REFERENCES users(id),
                   FOREIGN KEY (problem_id) REFERENCES problems(id),
                   FOREIGN KEY (submission_id) REFERENCES submissions(id)
                   )
            """)
    
    conn.commit()
    conn.close()
    print("สร้างฐานข้อมูลสำเร็จ")

def seed_problems():
    """ใส่โจทย์ตัวอย่าง 5 ข้อ"""
    conn = get_db()
    cursor = conn.cursor()

    # เช็คว่ามีโจทย์อยู่แล้วหรือยัง
    cursor.execute("SELECT COUNT(*) FROM problems")
    count = cursor.fetchone()[0]
    if count > 0:
        conn.close()
        return

    problems = [
        (
            "สวัสดีโลก",
            "เขียนโปรแกรมพิมพ์คำว่า Hello World",
            "output", "easy"
        ),
        (
            "บวกเลขสองจำนวน",
            "รับตัวเลข 2 จำนวนจาก input แล้วพิมพ์ผลบวก\n\nตัวอย่าง:\nInput: 3 5\nOutput: 8",
            "input-output", "easy"
        ),
        (
            "เลขคู่หรือเลขคี่",
            "รับตัวเลข 1 จำนวน พิมพ์ว่า Even หรือ Odd\n\nตัวอย่าง:\nInput: 4\nOutput: Even",
            "condition", "easy"
        ),
        (
            "ผลรวม 1 ถึง N",
            "รับตัวเลข N พิมพ์ผลรวม 1+2+3+...+N\n\nตัวอย่าง:\nInput: 5\nOutput: 15",
            "loop", "easy"
        ),
        (
            "ฟังก์ชันหาค่าสูงสุด",
            "รับตัวเลข 3 จำนวนในบรรทัดเดียว พิมพ์ค่าที่มากที่สุด\n\nตัวอย่าง:\nInput: 3 7 2\nOutput: 7",
            "function", "medium"
        ),
    ]

    for title, desc, cat, diff in problems:
        cursor.execute(
            "INSERT INTO problems (title, description, category, difficulty) VALUES (?,?,?,?)",
            (title, desc, cat, diff)
        )

    conn.commit()

    # ใส่ test cases ของแต่ละโจทย์
    test_cases = [
        # โจทย์ 1 — Hello World
        (1, "", "Hello World", 0),

        # โจทย์ 2 — บวกเลข
        (2, "3 5",  "8",  0),
        (2, "10 20", "30", 1),
        (2, "0 0",  "0",  1),

        # โจทย์ 3 — เลขคู่คี่
        (3, "4", "Even", 0),
        (3, "7", "Odd",  0),
        (3, "0", "Even", 1),

        # โจทย์ 4 — ผลรวม 1 ถึง N
        (4, "5",  "15", 0),
        (4, "10", "55", 1),

        # โจทย์ 5 — ค่าสูงสุด
        (5, "3 7 2", "7", 0),
        (5, "1 1 1", "1", 1),
        (5, "9 2 5", "9", 1),
    ]

    cursor.executemany(
        "INSERT INTO test_cases (problem_id, input_data, expected, is_hidden) VALUES (?,?,?,?)",
        test_cases
    )

    conn.commit()
    conn.close()
    print("✅ ใส่โจทย์ตัวอย่างสำเร็จ")

if __name__ == "__main__":
    init_db()
    seed_problems()
    print("เสร็จ!")