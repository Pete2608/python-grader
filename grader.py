import docker
import os
import re
import ast
import time

# โครงสร้างที่โจทย์ "กำหนดไว้" (คอลัมน์ problems.required_structure) -> (โหนด AST ที่ต้องมีอย่างน้อยหนึ่งชนิด, คำแนะนำ)
# ใช้เฉพาะโจทย์ที่กำหนดโครงสร้างไว้ ไม่ใช้กับโจทย์ที่อนุญาตให้แก้ปัญหาได้หลายวิธี (ค่า NULL = ไม่ตรวจ)
# ผลเป็นคำแนะนำเท่านั้น ไม่มีผลต่อการตัดสินผ่าน/ไม่ผ่าน
REQUIRED_STRUCTURE = {
    "if":   ({"If", "IfExp"},
             "โจทย์นี้กำหนดให้ใช้เงื่อนไข (if) แต่ไม่พบในซอร์สโค้ดของคุณ"),
    "loop": ({"For", "While"},
             "โจทย์นี้กำหนดให้ใช้ Loop (for/while) แต่ไม่พบในซอร์สโค้ดของคุณ"),
    "def":  ({"FunctionDef"},
             "โจทย์นี้กำหนดให้นิยามฟังก์ชัน (def) แต่ไม่พบในซอร์สโค้ดของคุณ"),
}


# จัดกลุ่มชื่อ Exception จริง (exception_name) เข้าเป็น 5 กลุ่มสำหรับการแสดงผล
# บนแดชบอร์ด (error_type) ตามตารางที่ 4 ของโครงร่างปัญหาพิเศษ
# ชื่อ Exception ที่ไม่อยู่ใน 5 กลุ่มนี้ (เช่น TimeoutError) จะใช้ "Other Exception"
# TabError เป็นคลาสย่อยของ IndentationError จึงจัดเข้ากลุ่ม IndentationError แต่ระบบ
# ยังตรวจชื่อ Exception แบบตรงตัว (exact match) เพื่อไม่ให้ IndentationError/TabError
# ถูกจัดเป็น SyntaxError แม้ทั้งคู่จะเป็นคลาสย่อยของ SyntaxError ก็ตาม
ERROR_TYPE_GROUPS = {
    "SyntaxError":      "SyntaxError",
    "IndentationError": "IndentationError",
    "TabError":         "IndentationError",
    "NameError":        "NameError",
    "TypeError":        "TypeError",
    "IndexError":       "Index/Value Error",
    "ValueError":       "Index/Value Error",
}


def classify_error_type(exception_name):
    """จัดกลุ่ม exception_name เป็น error_type สำหรับแสดงผล — ชื่อ Exception ที่ไม่อยู่ใน
    5 กลุ่มหลัก (เช่น ZeroDivisionError, KeyError) จะถูกจัดเป็น "Other Exception" และไม่รวม
    ในการทดสอบความถูกต้องของการจำแนก (หัวข้อ 11.1.2 ของโครงร่างปัญหาพิเศษ)"""
    return ERROR_TYPE_GROUPS.get(exception_name, "Other Exception")


# คำที่บ่งชี้ว่า stderr มาจากการเชื่อมต่อเครือข่ายที่ถูก Docker ปฏิเสธ
# (network_disabled=True ใน run_code) ใช้จำแนกสถานะ "Security Violation"
# ตามตารางที่ 5/9 ของโครงร่างปัญหาพิเศษ
SECURITY_VIOLATION_KEYWORDS = (
    "network is unreachable",
    "newconnectionerror",
    "connection refused",
    "name or service not known",
    "temporary failure in name resolution",
    "no route to host",
)


def is_security_violation(stderr_text):
    if not stderr_text:
        return False
    text = stderr_text.lower()
    return any(kw in text for kw in SECURITY_VIOLATION_KEYWORDS)


def ast_check(code, required_structure=None):
    result = {
        "passed":   True,
        "errors":   [],
        "warnings": []
    }

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        result["passed"] = False
        result["errors"].append(
            f"SyntaxError: บรรทัดที่ {e.lineno} — {e.msg}"
        )
        return result

    node_types = set()
    for node in ast.walk(tree):
        node_types.add(type(node).__name__)

    required = REQUIRED_STRUCTURE.get(required_structure)
    if required and not (required[0] & node_types):
        result["warnings"].append(required[1])

    allowed_short = {"i", "j", "k", "n", "x", "y", "z"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            name = node.id
            if len(name) == 1 and name not in allowed_short:
                result["warnings"].append(
                    f"ชื่อตัวแปร '{name}' เป็นตัวอักษรเดียว ควรตั้งชื่อที่อ่านแล้วเข้าใจ"
                )
                break

    return result


def run_code(code, input_data="", timeout=2):
    client = docker.from_env()

    try:
        client.ping()
    except docker.errors.DockerException:
        return {
            "output":            "",
            "error":             "ไม่สามารถเชื่อมต่อ Docker ได้",
            "is_error":          True,
            "exit_code":         None,
            "execution_time_ms": None
        }

    container = None
    start = time.monotonic()
    try:
        # สร้าง container
        container = client.containers.create(
            image="python-sandbox",
            command=["python", "-c", code],
            stdin_open=True,
            mem_limit="128m",
            nano_cpus=500_000_000,
            network_disabled=True,
        )

        # start container
        container.start()

        # ส่ง input เข้า container ถ้ามี
        if input_data:
            sock = container.attach_socket(
                params={"stdin": 1, "stream": 1}
            )
            import socket
            try:
                sock._sock.send(input_data.encode("utf-8") + b"\n")
            except:
                sock.send(input_data.encode("utf-8") + b"\n")
            finally:
                sock.close()

        # รอผลลัพธ์พร้อม timeout (วินาที)
        wait_result = container.wait(timeout=timeout)
        execution_time_ms = int((time.monotonic() - start) * 1000)
        exit_code = wait_result.get("StatusCode") if isinstance(wait_result, dict) else wait_result

        # ดึง logs ทั้ง stdout และ stderr
        stdout = container.logs(stdout=True,  stderr=False).decode("utf-8")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8")

        if stderr:
            return {
                "output":             stdout,
                "error":              stderr,
                "is_error":           True,
                "is_security_violation": is_security_violation(stderr),
                "exit_code":          exit_code,
                "execution_time_ms":  execution_time_ms
            }

        return {
            "output":            stdout,
            "error":             None,
            "is_error":          False,
            "is_security_violation": False,
            "exit_code":         exit_code,
            "execution_time_ms": execution_time_ms
        }

    except Exception as e:
        execution_time_ms = int((time.monotonic() - start) * 1000)
        error_msg = str(e)
        if "timed out" in error_msg.lower() or "read timeout" in error_msg.lower():
            return {
                "output":            "",
                "error":             "TimeoutError: โค้ดใช้เวลานานเกินไป อาจเกิดจาก infinite loop",
                "is_error":          True,
                "is_security_violation": False,
                "exit_code":         None,
                "execution_time_ms": execution_time_ms
            }
        return {
            "output":            "",
            "error":             error_msg,
            "is_error":          True,
            "is_security_violation": False,
            "exit_code":         None,
            "execution_time_ms": execution_time_ms
        }

    finally:
        if container:
            try:
                container.remove(force=True)
            except:
                pass


def extract_error_type(error_message):
    """จำแนกประเภทข้อผิดพลาดตาม 5 กลุ่มหลักของโครงงาน
    (SyntaxError, IndentationError, NameError, TypeError, IndexError/ValueError)

    ต้องอ่านจาก "บรรทัดสุดท้าย" ของ Traceback เท่านั้น เพราะรูปแบบจริงของ
    Python คือ "ExceptionType: message" อยู่บรรทัดท้ายสุดเสมอ
    ถ้าใช้ re.search หาแบบจับคู่แรกที่เจอในข้อความทั้งหมด จะจับผิดประเภทได้
    เช่น โค้ดผู้เรียนมีฟังก์ชันชื่อ raiseTypeError() แล้วเกิด NameError ที่อื่น
    เฟรมก่อนหน้าที่พิมพ์ "in raiseTypeError" จะถูกจับเป็น error type ผิดๆ
    """
    if not error_message:
        return "UnknownError"

    lines = [line.strip() for line in error_message.strip().splitlines() if line.strip()]

    for line in reversed(lines):
        match = re.match(r"^(\w+(?:Error|Exception))\b", line)
        if match:
            return match.group(1)

    return "UnknownError"


def extract_error_line(error_message):
    """หาเลขบรรทัดที่เกิดข้อผิดพลาดจริง คือเฟรมสุดท้าย (in-most) ของ Traceback
    ไม่ใช่เฟรมแรกที่เจอ เพราะ Traceback แสดงจาก "most recent call last"
    """
    if not error_message:
        return None
    matches = re.findall(r"line (\d+)", error_message)
    if matches:
        return int(matches[-1])
    return None


def grade_submission(code, problem_id, user_id, conn):

    # MySQL ต้องสร้าง cursor ก่อนทุกครั้ง
    # ไม่มี conn.execute() แบบ SQLite
    cursor = conn.cursor()

    # ดึงข้อมูลโจทย์ — MySQL ใช้ %s แทน ?
    cursor.execute("SELECT * FROM problems WHERE id = %s", (problem_id,))
    problem  = cursor.fetchone()
    required_structure = problem.get("required_structure") if problem else None

    # ดึง test cases ทั้งหมด
    cursor.execute(
        "SELECT * FROM test_cases WHERE problem_id = %s", (problem_id,)
    )
    test_cases = cursor.fetchall()

    results         = []
    ast_warnings    = []
    exception_name  = None
    error_message   = None
    error_line      = None

    # AST check ก่อนรันโค้ดจริง
    ast_result   = ast_check(code, required_structure)
    ast_warnings = ast_result["warnings"]

    if not ast_result["passed"]:
        error_message  = "\n".join(ast_result["errors"])
        exception_name = "SyntaxError"
        error_type     = classify_error_type(exception_name)
        status         = "Execution Error"

        cursor.execute(
            """INSERT INTO submissions
               (user_id, problem_id, code, status, stderr, test_case_summary)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, problem_id, code, status, error_message, "ไม่ได้ตรวจ (พบ SyntaxError ก่อนรัน)")
        )
        conn.commit()

        # MySQL ใช้ cursor.lastrowid แทน last_insert_rowid()
        submission_id = cursor.lastrowid

        cursor.execute(
            """INSERT INTO error_logs
               (submission_id, exception_name, error_type, error_message, error_line)
               VALUES (%s, %s, %s, %s, %s)""",
            (submission_id, exception_name, error_type, error_message, None)
        )
        conn.commit()
        cursor.close()

        return {
            "status":             status,
            "results":            [],
            "error_message":      error_message,
            "exception_name":     exception_name,
            "error_type":         error_type,
            "submission_id":      submission_id,
            "ast_warnings":       ast_warnings,
            "execution_time_ms":  None,
            "test_case_summary":  "ไม่ได้ตรวจ (พบ SyntaxError ก่อนรัน)"
        }

    # Dynamic Testing — หยุดที่ Test Case แรกที่ทำให้เกิด Exception
    # จึงบันทึกเฉพาะข้อผิดพลาดหลักของการส่งครั้งนั้น (1 submission : 0..1 error_logs)
    status            = "Passed"
    stdout_text       = ""
    stderr_text       = ""
    exit_code         = None
    execution_time_ms = None
    passed_count      = 0

    for tc in test_cases:
        timeout = problem["timeout_sec"] if problem.get("timeout_sec") else 2
        run_result = run_code(code, tc["input_data"], timeout=timeout)
        exit_code         = run_result.get("exit_code")
        execution_time_ms = run_result.get("execution_time_ms")

        if run_result["is_error"]:
            stderr_text    = run_result["error"]
            error_message  = stderr_text
            exception_name = extract_error_type(stderr_text)
            error_line     = extract_error_line(stderr_text)

            if exception_name == "TimeoutError":
                status = "Timeout"
            elif run_result.get("is_security_violation"):
                status = "Security Violation"
            else:
                status = "Execution Error"

            results.append({
                "input":    tc["input_data"],
                "expected": tc["expected_output"],
                "got":      "ERROR",
                "passed":   False,
                "hidden":   tc["is_hidden"]
            })
            break

        else:
            stdout_text = run_result["output"]
            got      = run_result["output"].strip()
            expected = tc["expected_output"].strip()
            passed   = (got == expected)

            if passed:
                passed_count += 1

            results.append({
                "input":    tc["input_data"],
                "expected": expected,
                "got":      got,
                "passed":   passed,
                "hidden":   tc["is_hidden"]
            })

    total_cases = len(results)
    if status == "Passed" and passed_count < total_cases:
        status = "Wrong Answer"

    test_case_summary = (
        f"ผ่าน {passed_count} จาก {total_cases} Test Case" if total_cases else "ไม่มี Test Case"
    )

    cursor.execute(
        """INSERT INTO submissions
           (user_id, problem_id, code, status, stdout, stderr,
            exit_code, execution_time_ms, test_case_summary)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (user_id, problem_id, code, status, stdout_text, stderr_text,
         exit_code, execution_time_ms, test_case_summary)
    )
    conn.commit()

    # MySQL ใช้ cursor.lastrowid
    submission_id = cursor.lastrowid

    # บันทึก Error Log เฉพาะสถานะ Execution Error เท่านั้น เพราะ Timeout และ
    # Security Violation เป็นสถานะการตัดสินของระบบ ไม่ใช่ Exception Type
    # (ตามคำจำกัดความในโครงร่างปัญหาพิเศษ) จึงไม่จัดกลุ่มเข้า error_type 5 กลุ่ม
    # และไม่นับในกราฟ Error Frequency
    error_type = None
    if status == "Execution Error" and error_message:
        error_type = classify_error_type(exception_name)

        cursor.execute(
            """INSERT INTO error_logs
               (submission_id, exception_name, error_type, error_message, error_line)
               VALUES (%s, %s, %s, %s, %s)""",
            (submission_id, exception_name, error_type, error_message, error_line)
        )
        conn.commit()

    # ตัวชี้วัดผลการส่งโปรแกรม ตามหัวข้อ 5.1.1 ของโครงร่างปัญหาพิเศษ
    # ได้แก่ SuccessRate, ExecutionErrorRate และ FirstAttemptRate (หน่วยเป็นร้อยละ)
    # ใช้แสดง "แนวโน้ม" การเปลี่ยนแปลงของผลการส่งโปรแกรม
    # ไม่ใช่คะแนนวัดความสามารถที่ผ่านการตรวจสอบแล้ว
    performance_metrics = calc_performance_metrics(cursor, user_id)

    cursor.close()

    return {
        "status":               status,
        "results":              results,
        "error_message":        error_message,
        "exception_name":       exception_name,
        "error_type":           error_type,
        "submission_id":        submission_id,
        "ast_warnings":         ast_warnings,
        "execution_time_ms":    execution_time_ms,
        "test_case_summary":    test_case_summary,
        "success_rate":         performance_metrics["success_rate"],
        "execution_error_rate": performance_metrics["execution_error_rate"],
        "first_attempt_rate":   performance_metrics["first_attempt_rate"]
    }


def calc_performance_metrics(cursor, user_id):
    """คำนวณ SuccessRate, ExecutionErrorRate และ FirstAttemptRate ของผู้เรียนคนหนึ่ง
    ตามคำนิยามในหัวข้อ 5.1.1 ของโครงร่างปัญหาพิเศษ

    ExecutionErrorRate นับสถานะ Execution Error, Timeout และ Security Violation
    รวมกัน (ตารางที่ 5 — สถานะที่ "นับใน Execution Error Rate")
    """
    cursor.execute(
        "SELECT status FROM submissions WHERE user_id = %s",
        (user_id,)
    )
    all_submissions = cursor.fetchall()
    total = len(all_submissions)

    if total == 0:
        return {"success_rate": 0.0, "execution_error_rate": 0.0, "first_attempt_rate": 0.0}

    passed_count = sum(1 for r in all_submissions if r["status"] == "Passed")
    execution_error_count = sum(
        1 for r in all_submissions
        if r["status"] in ("Execution Error", "Timeout", "Security Violation")
    )

    success_rate         = round(passed_count / total * 100, 1)
    execution_error_rate = round(execution_error_count / total * 100, 1)

    # FirstAttemptRate — สัดส่วนโจทย์ที่ผ่านตั้งแต่ครั้งแรกที่ส่ง
    # ใช้ MIN(id) แทน MIN(submitted_at) เพื่อกันปัญหาเวลาซ้ำกัน
    cursor.execute(
        """SELECT s.status
           FROM submissions s
           INNER JOIN (
               SELECT problem_id, MIN(id) AS first_id
               FROM submissions
               WHERE user_id = %s
               GROUP BY problem_id
           ) f ON s.id = f.first_id""",
        (user_id,)
    )
    first_attempts = cursor.fetchall()
    total_problems = len(first_attempts)
    first_passed   = sum(1 for r in first_attempts if r["status"] == "Passed")
    first_attempt_rate = round(first_passed / total_problems * 100, 1) if total_problems else 0.0

    return {
        "success_rate":         success_rate,
        "execution_error_rate": execution_error_rate,
        "first_attempt_rate":   first_attempt_rate
    }


if __name__ == "__main__":
    print("=== ทดสอบ run_code() ===\n")

    result = run_code('print("Hello World")')
    print(f"ทดสอบ 1 — โค้ดถูก:")
    print(f"  output:   {repr(result['output'])}")
    print(f"  is_error: {result['is_error']}\n")

    result = run_code("print(x)")
    print(f"ทดสอบ 2 — NameError:")
    print(f"  error:    {result['error'][:60]}...")
    print(f"  is_error: {result['is_error']}\n")

    result = run_code("print('hello'")
    print(f"ทดสอบ 3 — SyntaxError:")
    print(f"  error_type: {extract_error_type(result['error'])}\n")

    result = run_code("while True: pass")
    print(f"ทดสอบ 4 — Timeout:")
    print(f"  error_type: {extract_error_type(result['error'])}\n")

    result = run_code("a, b = map(int, input().split())\nprint(a + b)", "3 5")
    print(f"ทดสอบ 5 — Input/Output:")
    print(f"  output: {repr(result['output'])}")
    print(f"  คาดหวัง: '8'")
    print(f"  ผ่าน: {result['output'].strip() == '8'}")