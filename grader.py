import subprocess
import tempfile
import os
import traceback
import re
import ast

def ast_check(code, category=""):
    """
    Parameters:
      code     → โค้ด Python ของผู้เรียน
      category → หมวดหมู่โจทย์ เช่น "loop", "function"
                 ใช้ตรวจว่าโค้ดใช้โครงสร้างที่ถูกต้องไหม

    Returns dict:
      {
        "passed":   True/False,
        "errors":   list ของปัญหาที่พบ,
        "warnings": list ของคำเตือน (ไม่ทำให้ fail)
      }
    """
    result = {
        "passed":   True,
        "errors":   [],
        "warnings": []
    }
    # ตรวง SyntaxError
    try:
        tree = ast.parse(code) # แปลง code เป็นต้นไม้(tree) แล้วเก็บไว้ในตัวแปร tree
    except SyntaxError as e:
        result["passed"] = False
        result["errors"].append(
            f"SyntaxError: บรรทัดที่ {e.lineno} — {e.msg}"
        )
        return result # ถ้า SyntaxError ให้หยุดเลย
    
    
    node_types = set()
    for node in ast.walk(tree): # ast.walk() เป็นการเช็คทุก Node ใน tree
        node_types.add(type(node).__name__) # type(node).__name__ คือชื่อของ Node เช่น "For", "While"
    
    # ตรวจตามหมวดหมู่ของโจทย์
    # ถ้าโจทย์กำหนดว่าต้องใช้ loop แต่ผู้เรียนไม่ได้ใช้ → warning
    if category == "loop":
        has_loop = ("For" in node_types or "While" in node_types) # ตรวจว่ามี For หรือ While รึป่าว
        if not has_loop: # ถ้าไม่มี → warning
            result["warnings"].append(
                "⚠️ โจทย์นี้ควรใช้ Loop (for/while) แต่ไม่พบในโค้ดของคุณ"
            )
    
    if category == "function":
        has_func = "FunctionDef" in node_types # ตรวจว่ามี Function
        if not has_func: # ถ้าไม่มี → warning
            result["warnings"].append(
                "⚠️ โจทย์นี้ควรนิยาม Function (def) แต่ไม่พบในโค้ดของคุณ"
            )

    # ตรวจชื่อตัวแปรที่สั้นเกินไป (1 ตัวอักษร ยกเว้น i, j, k, n)
    allowed_short = {"i", "j", "k", "n", "x", "y", "z"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name): # isinstance คือการตรวจว่าเป็นประเภทที่ระบุหรือไม่ เช่น isinstance(node, str) node เป็น str หรือไม่
            name = node.id
            if len(name) == 1 and name not in allowed_short:
                result["warnings"].append(
                    f"💡 ตัวแปรชื่อ '{name}' สั้นเกินไป ควรตั้งชื่อที่อ่านแล้วเข้าใจ"
                )
                break  # แจ้งแค่ครั้งเดียวพอ

    return result

# run_code
def run_code(code, input_data=""):
    temp_path = None
    try:
        # สร้าง tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", # กำหนดให้แก้ไขได้
            suffix=".py", # สกุล .py
            delete=False, # ไม่ต้องลบทันที
            encoding="utf-8" # ภาษาไทย
        ) as f:
            f.write(code) # ให้เขียนโค้ดลงไฟล์
            temp_path = f.name # จำ path ของ temp
    
        # run subprocess
        result = subprocess.run(
                ["python", temp_path], # คำสั่ง
                input=input_data, # ข้อมูลที่นำเข้า
                capture_output=True, # เก็บผลลัพธ์ กับ error log ไว้
                text=True, # เก็บเป็น string
                timeout=2 # runtime 2 วิกัน infinite loop
        )
        # ถ้า error
        if result.stderr:
            return {
                "output": "",
                "error": result.stderr,
                "is_error": True
            }
        # ถ้าไม่ error
        return {
                "output": result.stdout,
                "error": None,
                "is_error": False
            }
    # subprocess runtime เกิน 2วิ timeout
    except subprocess.TimeoutExpired:
        return {
            "output":   "",
            "error":    "TimeoutError: โค้ดใช้เวลานานเกินไป (เกิน 2 วินาที) อาจเกิดจาก infinite loop",
            "is_error": True
        }
    # ถ้าเกิด error อื่น
    except Exception as e:
        return {
            "output":   "",
            "error":    str(e),
            "is_error": True
        }

    # ลบ filetemp
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

# extract_error_type แยกประเภท error
def extract_error_type(error_massage):
    if not error_massage:
        return "UnknownError"
    
    # ใช้หา error เช่น NameError
    pattern = r"(\w+Error|\w+Exception)" # r = raw string (ไม่แปลง \ เช่น \n \t \w)
    match = re.search(pattern, error_massage) 
    # ใช้เงื่อนไข error ใน pattern เพื่อหาว่า error อะไรใน error_massage

    if match:
        return match.group(1) # ให้ return แค่ชื่อ
    
    if "TimeoutError" in error_massage:
        return "TimeoutError"
    

    return "UnknownError"

# เอาไว้ดูเลขบรรทัดที่ error
def extract_error_line(error_message):
    if not error_message:
        return "UnknownError"
    
    # ใช้หา บรรทัดที่เกิด error
    pattern = r"line (\d+)" # \d+ เป็นเลข 0-9 ส่วน + คือต้องมี1ตัวขึ้นไป
    match = re.search(pattern, error_message)

    if match:
        return int(match.group(1))
    
    return None

# grade_submission รับโค้ดกับ problem_id แล้วตรวจกับ test case แล้วบันทึกลง DB
def grade_submission(code, problem_id, user_id, conn):
    
    # ดึงข้อมูลโจทย์ด้วย เพื่อรู้ category สำหรับ AST check
    problem = conn.execute(
        "SELECT * FROM problems WHERE id = ?", (problem_id,)
    ).fetchone()
    category = problem["category"] if problem else ""

    # ดึง testcase
    test_case = conn.execute(
        "SELECT * FROM test_cases WHERE problem_id = ?",
        (problem_id,)
    ).fetchall() # ใช้เพื่อดึงข้อมูลทั้งหมดที่เลือกจาก Select ลงตัวแปล

    # เก็บผลลัพธ์เป็นค่า default 
    all_passed     = True   # ผ่านทุกข้อไหม
    has_error      = False  # มี error ไหม
    error_message  = None   # ข้อความ error
    results        = []     # ผลแต่ละ test case สำหรับแสดงผล
    ast_warnings  = []      # ใช้เก็บ warning จาก AST

    # ast check ก่อน run code
    ast_result = ast_check(code, category)

    # เก็บ warnings ไว้แสดง
    ast_warnings = ast_result["warnings"]

    if not ast_result["passed"]:
        error_message = "\n".join(ast_result["errors"])
        has_error     = True

        # บันทึกลง submissions
        conn.execute(
            """INSERT INTO submissions
               (user_id, problem_id, code, status)
               VALUES (?, ?, ?, ?)""",
            (user_id, problem_id, code, "error")
        )
        conn.commit()

        submission_id = conn.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

        # บันทึกลง error_logs
        conn.execute(
            """INSERT INTO error_logs
               (user_id, problem_id, submission_id,
                error_type, error_message, error_line)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, problem_id, submission_id,
             "SyntaxError", error_message,
             None)
        )
        conn.commit()

        return {
            "status":        "error",
            "results":       [],
            "error_message": error_message,
            "error_type":    "SyntaxError",
            "submission_id": submission_id,
            "ast_warnings":  ast_warnings   # ← ส่ง warnings กลับด้วย
        }

    for tc in test_case:
        # รันโค้ดกับ input ของ test case นี้
        run_result = run_code(code, tc["input_data"])

        if run_result["is_error"]:
            # โค้ดแตก
            has_error = True
            all_passed = False
            error_message = run_result["error"]

            # มันคือการเอาผลลัพธ์ของ test case นี้ไปเก็บใน results
            results.append({
                "input":    tc["input_data"],
                "expected": tc["expected"],
                "got":      "ERROR",
                "passed":   False,
                "hidden":   tc["is_hidden"]
            })
            # ถ้าเกิด error หยุดวนลูปเลย ไม่ต้องรัน test case ที่เหลือ
            break
        
        else:
            # ถ้าไม่ error จะเทียบ output กับ expected
            got = run_result["output"].strip() # .strip() ใช้เพื่อตัดช่องว่างกับขึ้นบรรทัดไชใหม่
            # แล้ว output ก็เอามาจากฟังชั้น run_code
            expected = tc["expected"].strip()
            passed   = (got == expected)

            if not passed: # ถ้า passed เป็น false ก็จะเข้าเงื่อนไขเพราะ not ทำให้เป็นจริง
                all_passed = False
            
            results.append({
                "input":    tc["input_data"],
                "expected": expected,
                "got":      got,
                "passed":   passed,
                "hidden":   tc["is_hidden"]
            })

    if has_error:
        status = "error"
    elif all_passed:
        status = "passed"
    else:
        status = "failed"
    # เพิ่มข้อมูลลงตาราง submission
    conn.execute(
        """INSERT INTO submissions
           (user_id, problem_id, code, status)
           VALUES (?, ?, ?, ?)""",
        (user_id, problem_id, code, status)
    )
    conn.commit()

    # ดึงแค่ id จากตาราง submission ที่เพิ่มเข้ามาอันล่าสุด
    submission_id = conn.execute(
        "SELECT last_insert_rowid()"
    ).fetchone()[0]

    # เช็ค error ถ้ามีเก็บ log ลง DB
    if has_error and error_message:
        error_type = extract_error_type(error_message) # เรียกฟังชั่นดูประเภท error
        error_line = extract_error_line(error_message) # เรียกฟังชั่นดูบรรทัด error

        # เก็บ log error ลง DB
        conn.execute(
            """INSERT INTO error_logs
               (user_id, problem_id, submission_id,
                error_type, error_message, error_line)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, problem_id, submission_id,
             error_type, error_message, error_line)
        )
        conn.commit()

        # คืนผลลัพธ์กลีบไปให้ app.py
        return {
        "status":       status,
        "results":      results,
        "error_message": error_message,
         # ถ้ามี error → ดึงประเภท error
         # ถ้าไม่มี → คืน None
        "error_type":   extract_error_type(error_message) if error_message else None,
        "submission_id": submission_id,
        "ast_warnings":  ast_warnings
    }
    return {
        "status":       status,
        "results":      results,
        "error_message": error_message,
         # ถ้ามี error → ดึงประเภท error
         # ถ้าไม่มี → คืน None
        "error_type":   extract_error_type(error_message) if error_message else None,
        "submission_id": submission_id,
        "ast_warnings":  ast_warnings}

if __name__ == "__main__":
    print("=== ทดสอบ run_code() ===\n")

    # ทดสอบ 1: โค้ดถูกต้อง
    result = run_code('print("Hello World")')
    print(f"ทดสอบ 1 — โค้ดถูก:")
    print(f"  output:   {repr(result['output'])}")
    print(f"  is_error: {result['is_error']}\n")

    # ทดสอบ 2: โค้ดมี NameError
    result = run_code("print(x)")
    print(f"ทดสอบ 2 — NameError:")
    print(f"  error:    {result['error'][:60]}...")

    print(f"  is_error: {result['is_error']}\n")

    # ทดสอบ 3: โค้ดมี SyntaxError
    result = run_code("print('hello'")
    print(f"ทดสอบ 3 — SyntaxError:")
    print(f"  error_type: {extract_error_type(result['error'])}\n")

    # ทดสอบ 4: โค้ด Infinite Loop (ทดสอบ timeout)
    result = run_code("while True: pass")
    print(f"ทดสอบ 4 — Timeout:")
    print(f"  error_type: {extract_error_type(result['error'])}\n")

    # ทดสอบ 5: โค้ดรับ input
    result = run_code("a, b = map(int, input().split())\nprint(a + b)", "3 5")
    print(f"ทดสอบ 5 — Input/Output:")
    print(f"  output: {repr(result['output'])}")
    print(f"  คาดหวัง: '8'")
    print(f"  ผ่าน: {result['output'].strip() == '8'}")