import pymysql
from dotenv import load_dotenv
import os
import sys

from grader import ERROR_TYPE_GROUPS

# โหลดค่าจากไฟล์ .env
load_dotenv()

# กันโปรแกรม crash ตอน print ข้อความที่มีอิโมจิ/ภาษาไทย บน Windows console
# ที่ใช้ codepage แบบ cp874 (เช่น cmd.exe เริ่มต้น) ซึ่งเข้ารหัส UTF-8 ไม่ได้
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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

def migrate_users_password_column(cursor):
    """เปลี่ยนชื่อคอลัมน์ users.password -> password_hash ให้ตรงกับ ER Diagram
    ที่แก้ไข (หัวข้อ 11.1.2 ของโครงร่างปัญหาพิเศษ) โดยไม่ทำลายข้อมูลเดิม"""
    cursor.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'"
    )
    cols = {row["COLUMN_NAME"] for row in cursor.fetchall()}
    if "password" in cols and "password_hash" not in cols:
        cursor.execute(
            "ALTER TABLE users CHANGE COLUMN password password_hash VARCHAR(255) NOT NULL"
        )


def migrate_test_cases_expected_column(cursor):
    """เปลี่ยนชื่อคอลัมน์ test_cases.expected -> expected_output ให้ตรงกับ ER Diagram"""
    cursor.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'test_cases'"
    )
    cols = {row["COLUMN_NAME"] for row in cursor.fetchall()}
    if "expected" in cols and "expected_output" not in cols:
        cursor.execute(
            "ALTER TABLE test_cases CHANGE COLUMN expected expected_output TEXT NOT NULL"
        )


def migrate_submissions_columns(cursor):
    """เพิ่มคอลัมน์ stdout, stderr, exit_code, execution_time_ms, test_case_summary
    ให้ตาราง submissions ตามโครงสร้างในตารางที่ 1 ของโครงร่างปัญหาพิเศษ"""
    cursor.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'submissions'"
    )
    cols = {row["COLUMN_NAME"] for row in cursor.fetchall()}
    additions = [
        ("stdout",             "TEXT NULL"),
        ("stderr",             "TEXT NULL"),
        ("exit_code",          "INT NULL"),
        ("execution_time_ms",  "INT NULL"),
        ("test_case_summary",  "VARCHAR(50) NULL"),
    ]
    for name, ddl in additions:
        if name not in cols:
            cursor.execute(f"ALTER TABLE submissions ADD COLUMN {name} {ddl}")


def _drop_fk_if_exists(cursor, table, column):
    cursor.execute(
        "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s "
        "AND REFERENCED_TABLE_NAME IS NOT NULL",
        (table, column)
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(f"ALTER TABLE {table} DROP FOREIGN KEY {row['CONSTRAINT_NAME']}")


def migrate_error_logs_schema(cursor):
    """ปรับ error_logs ให้ตรงกับ ER Diagram ที่แก้ไข (หัวข้อ 11.1.2 ของโครงร่างปัญหาพิเศษ):
    ไม่เก็บ user_id/problem_id ซ้ำจาก submissions เพราะดึงได้ผ่าน submission_id อยู่แล้ว
    และเพิ่ม exception_name (ชื่อ Exception จริงตามที่ Python รายงาน) แยกจาก error_type
    (กลุ่มที่ใช้แสดงผลบนแดชบอร์ด 5 กลุ่มตามตารางที่ 4)"""
    cursor.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'error_logs'"
    )
    cols = {row["COLUMN_NAME"] for row in cursor.fetchall()}

    if "exception_name" not in cols:
        cursor.execute(
            "ALTER TABLE error_logs ADD COLUMN exception_name VARCHAR(100) NULL AFTER submission_id"
        )
        # ข้อมูลเดิม error_type เก็บชื่อ Exception จริงอยู่แล้ว (ไม่ได้จัดกลุ่ม)
        # จึงนำมาตั้งต้นเป็น exception_name ให้แถวเก่า
        cursor.execute("UPDATE error_logs SET exception_name = error_type WHERE exception_name IS NULL")

    for column in ("user_id", "problem_id"):
        if column in cols:
            _drop_fk_if_exists(cursor, "error_logs", column)
            cursor.execute(f"ALTER TABLE error_logs DROP COLUMN {column}")


def migrate_required_structure(cursor):
    """เพิ่มคอลัมน์ required_structure (โครงสร้างที่โจทย์กำหนด: if | loop | def | NULL)
    ให้ฐานข้อมูลที่สร้างไว้ก่อนหน้า และกำหนดเฉพาะโจทย์ที่ระบุโครงสร้างไว้ในโจทย์จริง"""
    cursor.execute(
        "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'problems' "
        "AND COLUMN_NAME = 'required_structure'"
    )
    if cursor.fetchone()["c"] == 0:
        cursor.execute("ALTER TABLE problems ADD COLUMN required_structure VARCHAR(20) NULL")

    updates = [
        ("ผลรวม 1 ถึง N", "loop",
         "รับตัวเลข N พิมพ์ผลรวม 1+2+3+...+N โดยต้องใช้คำสั่งวนซ้ำ (for หรือ while)\n\nตัวอย่าง:\nInput: 5\nOutput: 15"),
        ("ฟังก์ชันหาค่าสูงสุด", "def",
         "เขียนฟังก์ชัน (def) รับตัวเลข 3 จำนวนในบรรทัดเดียว แล้วพิมพ์ค่าที่มากที่สุด\n\nตัวอย่าง:\nInput: 3 7 2\nOutput: 7"),
    ]
    for title, structure, desc in updates:
        cursor.execute(
            "UPDATE problems SET required_structure = %s, description = %s "
            "WHERE title = %s AND required_structure IS NULL",
            (structure, desc, title)
        )


def migrate_legacy_status_and_error_type(cursor):
    """ข้อมูลเก่าก่อนปรับระบบให้เป็น 5 สถานะ (Passed, Wrong Answer, Execution Error,
    Timeout, Security Violation) ยังมีค่า status แบบเดิม ('passed', 'failed', 'error')
    ค้างอยู่ใน submissions ทำให้ calc_performance_metrics() นับ SuccessRate กับ
    ExecutionErrorRate ไม่ตรง (เทียบ status แบบ case-sensitive กับชื่อสถานะปัจจุบัน
    ไม่เจอค่าที่สะกดคนละแบบ) จึงแปลงค่าเก่าให้ตรงกับชื่อสถานะปัจจุบัน:
    - 'passed' -> 'Passed'
    - 'error'  -> 'Execution Error' (แถวเหล่านี้มี error_logs ผูกอยู่จริง คือเกิด Exception)
    - 'failed' -> 'Wrong Answer' (รันจบโดยไม่เกิด Exception แต่ไม่มี error_logs ผูกอยู่)

    พร้อมกันนี้ error_type เก่าบางแถวเก็บชื่อ exception_name ดิบไว้ตรงๆ
    (เช่น ValueError, EOFError) โดยไม่ได้จัดกลุ่มเข้า 5 กลุ่มสำหรับการแสดงผลตามตารางที่ 4
    จึงคำนวณ error_type ใหม่จาก exception_name ทุกแถวด้วยกฎการจัดกลุ่มเดียวกับ
    grader.classify_error_type() เพื่อให้กราฟ Error Frequency ถูกต้อง"""
    cursor.execute("UPDATE submissions SET status = 'Passed' WHERE status = 'passed'")
    cursor.execute("UPDATE submissions SET status = 'Execution Error' WHERE status = 'error'")
    cursor.execute("UPDATE submissions SET status = 'Wrong Answer' WHERE status = 'failed'")

    cursor.execute("SELECT id, exception_name FROM error_logs")
    for row in cursor.fetchall():
        correct_type = ERROR_TYPE_GROUPS.get(row["exception_name"], "Other Exception")
        cursor.execute(
            "UPDATE error_logs SET error_type = %s WHERE id = %s",
            (correct_type, row["id"])
        )


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # ตาราง users
    # MySQL ใช้ AUTO_INCREMENT แทน AUTOINCREMENT
    # และใช้ INT แทน INTEGER
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INT PRIMARY KEY AUTO_INCREMENT,
            username      VARCHAR(100) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    migrate_users_password_column(cursor)

    # ตาราง problems
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS problems (
            id          INT PRIMARY KEY AUTO_INCREMENT,
            title       VARCHAR(255) NOT NULL UNIQUE,
            description TEXT NOT NULL,
            category    VARCHAR(100) NOT NULL,
            difficulty  VARCHAR(50) NOT NULL DEFAULT 'easy',
            timeout_sec INT NOT NULL DEFAULT 2,
            required_structure VARCHAR(20) NULL
        )
    """)

    migrate_required_structure(cursor)

    # ตาราง test_cases
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_cases (
            id              INT PRIMARY KEY AUTO_INCREMENT,
            problem_id      INT NOT NULL,
            input_data      TEXT NOT NULL,
            expected_output TEXT NOT NULL,
            is_hidden       INT NOT NULL DEFAULT 0,
            FOREIGN KEY (problem_id) REFERENCES problems(id)
        )
    """)
    migrate_test_cases_expected_column(cursor)

    # ตาราง submissions
    # stdout/stderr/exit_code/execution_time_ms/test_case_summary ตามโครงสร้าง
    # ข้อมูลบันทึกการส่งโปรแกรมในตารางที่ 1 ของโครงร่างปัญหาพิเศษ
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id                 INT PRIMARY KEY AUTO_INCREMENT,
            user_id            INT NOT NULL,
            problem_id         INT NOT NULL,
            code               TEXT NOT NULL,
            status             VARCHAR(50) NOT NULL,
            stdout             TEXT NULL,
            stderr             TEXT NULL,
            exit_code          INT NULL,
            execution_time_ms  INT NULL,
            test_case_summary  VARCHAR(50) NULL,
            submitted_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)    REFERENCES users(id),
            FOREIGN KEY (problem_id) REFERENCES problems(id)
        )
    """)
    migrate_submissions_columns(cursor)

    # ตาราง error_logs
    # ไม่เก็บ user_id/problem_id ซ้ำจาก submissions (ดึงได้ผ่าน submission_id)
    # exception_name = ชื่อ Exception จริง, error_type = กลุ่มที่ใช้แสดงผล (ตารางที่ 4)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS error_logs (
            id             INT PRIMARY KEY AUTO_INCREMENT,
            submission_id  INT NOT NULL,
            exception_name VARCHAR(100) NOT NULL,
            error_type     VARCHAR(100) NOT NULL,
            error_message  TEXT NOT NULL,
            error_line     INT,
            logged_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (submission_id) REFERENCES submissions(id)
        )
    """)
    migrate_error_logs_schema(cursor)
    migrate_legacy_status_and_error_type(cursor)

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

    # category ทั้ง 5 ตรงตามขอบเขตของโครงร่างปัญหาพิเศษ (หัวข้อ 5.1)
    # คือ 5 หัวข้อการเรียน: ตัวแปรและชนิดข้อมูล, นิพจน์และตัวดำเนินการ,
    # คำสั่งเงื่อนไข, คำสั่งวนซ้ำ, ฟังก์ชัน
    problems = [
        (
            "สวัสดีโลก",
            "เขียนโปรแกรมพิมพ์คำว่า Hello World",
            "ตัวแปรและชนิดข้อมูล", "easy"
        ),
        (
            "บวกเลขสองจำนวน",
            "รับตัวเลข 2 จำนวนจาก input แล้วพิมพ์ผลบวก\n\nตัวอย่าง:\nInput: 3 5\nOutput: 8",
            "นิพจน์และตัวดำเนินการ", "easy"
        ),
        (
            "เลขคู่หรือเลขคี่",
            "รับตัวเลข 1 จำนวน พิมพ์ว่า Even หรือ Odd\n\nตัวอย่าง:\nInput: 4\nOutput: Even",
            "คำสั่งเงื่อนไข", "easy"
        ),
        (
            "ผลรวม 1 ถึง N",
            "รับตัวเลข N พิมพ์ผลรวม 1+2+3+...+N\n\nตัวอย่าง:\nInput: 5\nOutput: 15",
            "คำสั่งวนซ้ำ", "easy"
        ),
        (
            "ฟังก์ชันหาค่าสูงสุด",
            "รับตัวเลข 3 จำนวนในบรรทัดเดียว พิมพ์ค่าที่มากที่สุด\n\nตัวอย่าง:\nInput: 3 7 2\nOutput: 7",
            "ฟังก์ชัน", "medium"
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
        "INSERT INTO test_cases (problem_id, input_data, expected_output, is_hidden) VALUES (%s, %s, %s, %s)",
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
