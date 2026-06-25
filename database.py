import pymysql
from dotenv import load_dotenv
import os

# โหลดค่าจากไฟล์ .env
load_dotenv()

def get_db():
    conn = pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor  # ดึงข้อมูลแบบ dict ได้เหมือน sqlite3.Row
    )
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # ตาราง users
    # MySQL ใช้ AUTO_INCREMENT แทน AUTOINCREMENT
    # และใช้ INT แทน INTEGER
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INT PRIMARY KEY AUTO_INCREMENT,
            username   VARCHAR(100) NOT NULL UNIQUE,
            password   VARCHAR(255) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ตาราง problems
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS problems (
            id          INT PRIMARY KEY AUTO_INCREMENT,
            title       VARCHAR(255) NOT NULL UNIQUE,
            description TEXT NOT NULL,
            category    VARCHAR(100) NOT NULL,
            difficulty  VARCHAR(50) NOT NULL DEFAULT 'easy',
            timeout_sec INT NOT NULL DEFAULT 2
        )
    """)

    # ตาราง test_cases
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_cases (
            id         INT PRIMARY KEY AUTO_INCREMENT,
            problem_id INT NOT NULL,
            input_data TEXT NOT NULL,
            expected   TEXT NOT NULL,
            is_hidden  INT NOT NULL DEFAULT 0,
            FOREIGN KEY (problem_id) REFERENCES problems(id)
        )
    """)

    # ตาราง submissions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id           INT PRIMARY KEY AUTO_INCREMENT,
            user_id      INT NOT NULL,
            problem_id   INT NOT NULL,
            code         TEXT NOT NULL,
            status       VARCHAR(50) NOT NULL,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)    REFERENCES users(id),
            FOREIGN KEY (problem_id) REFERENCES problems(id)
        )
    """)

    # ตาราง error_logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS error_logs (
            id            INT PRIMARY KEY AUTO_INCREMENT,
            user_id       INT NOT NULL,
            problem_id    INT NOT NULL,
            submission_id INT NOT NULL,
            error_type    VARCHAR(100) NOT NULL,
            error_message TEXT NOT NULL,
            error_line    INT,
            logged_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)       REFERENCES users(id),
            FOREIGN KEY (problem_id)    REFERENCES problems(id),
            FOREIGN KEY (submission_id) REFERENCES submissions(id)
        )
    """)

    # ตาราง participant_mapping (PDPA)
    # เก็บข้อมูลจริงของผู้เข้าร่วมแยกออกจากระบบหลัก
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS participant_mapping (
            id            INT PRIMARY KEY AUTO_INCREMENT,
            user_code     VARCHAR(20) NOT NULL UNIQUE,
            real_name     VARCHAR(255) NOT NULL,
            student_id    VARCHAR(20) NOT NULL,
            pretest_score INT DEFAULT 0,
            consented_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ สร้างฐานข้อมูลสำเร็จ")


def seed_problems():
    """ใส่โจทย์ตัวอย่าง 5 ข้อ"""
    conn = get_db()
    cursor = conn.cursor()

    # เช็คว่ามีโจทย์อยู่แล้วหรือยัง
    # MySQL + DictCursor คืนค่าเป็น dict จึงต้องดึงแบบนี้
    cursor.execute("SELECT COUNT(*) as count FROM problems")
    count = cursor.fetchone()["count"]
    if count > 0:
        cursor.close()
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

    # MySQL ใช้ %s แทน ?
    for title, desc, cat, diff in problems:
        cursor.execute(
            "INSERT INTO problems (title, description, category, difficulty) VALUES (%s, %s, %s, %s)",
            (title, desc, cat, diff)
        )

    conn.commit()

    # ใส่ test cases
    test_cases = [
        # โจทย์ 1 — Hello World
        (1, "", "Hello World", 0),

        # โจทย์ 2 — บวกเลข
        (2, "3 5",   "8",  0),
        (2, "10 20", "30", 1),
        (2, "0 0",   "0",  1),

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
        "INSERT INTO test_cases (problem_id, input_data, expected, is_hidden) VALUES (%s, %s, %s, %s)",
        test_cases
    )

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ ใส่โจทย์ตัวอย่างสำเร็จ")


if __name__ == "__main__":
    init_db()
    seed_problems()
    print("เสร็จ!")
