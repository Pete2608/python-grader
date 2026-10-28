# สรุปบริบทโปรเจกต์: ระบบตรวจคำตอบอัตโนมัติ Python (ปัญหาพิเศษ)

> ไฟล์นี้สร้างขึ้นเพื่อให้ Claude (แชทปกติบน claude.ai) เข้าใจบริบทของโปรเจกต์นี้
> โดยไม่ต้องอ่าน transcript ดิบจาก Claude Code วิธีใช้: แนบไฟล์นี้เข้าแชท
> หรือใส่เป็น Project Knowledge ใน claude.ai Projects

## ภาพรวมโปรเจกต์

ปัญหาพิเศษระดับปริญญาตรี สาขาวิทยาการคอมพิวเตอร์ มหาวิทยาลัยราชภัฏพิบูลสงคราม
ชื่อเรื่อง: "ระบบเว็บสำหรับวิเคราะห์ข้อผิดพลาดและติดตามแนวโน้มผลการส่งโปรแกรมภาษา Python
ของผู้เรียน" (A Web-Based System for Python Programming Error Analysis and Submission
Performance Trend Tracking)

**Stack**: Flask (Python) + MySQL (PyMySQL) + Docker Sandbox (รันโค้ดผู้เรียนแบบ
I/O Redirection, จำกัด CPU/Memory/Network) + Jinja2 + Chart.js + CodeMirror

**เอกสารอ้างอิง (ground truth ของทุกฟีเจอร์)**: `Phiraphat091069_ฉบับแก้ไข.docx`
ในโฟลเดอร์ `python_grader` — เป็นโครงร่างปัญหาพิเศษฉบับล่าสุดที่อาจารย์ที่ปรึกษาอนุมัติ
กฎสำคัญ: **demo หลักต้องไม่ทำอะไรเกินขอบเขตที่เขียนในเอกสารนี้เด็ดขาด**

## มี 2 โฟลเดอร์ demo แยกกันโดยเจตนา

| โฟลเดอร์ | จุดประสงค์ | กฎขอบเขต |
|---|---|---|
| `python_grader` | **demo หลัก** ใช้สอบ/ส่งจริง | ต้องตรงกับโครงร่าง .docx เท่านั้น ห้ามมีฟีเจอร์เกิน |
| `python_grader_wow` | demo เวอร์ชัน "เวอร์วังอะลังการ" โชว์ของ | ไม่ยึดขอบเขตเอกสาร ใส่ฟีเจอร์พิเศษได้เต็มที่ |

ฟีเจอร์ที่อยู่ใน `python_grader_wow` เท่านั้น (ห้ามเอาไปใส่ demo หลัก เพราะเกินขอบเขต):
- ตรวจ syntax แบบ real-time ขณะพิมพ์ (ก่อนกดส่ง) ผ่าน `/api/live_check`
- ตรวจความลึกของ if ที่ซ้อนกัน (nested-if depth warning)
- คำแนะนำแก้โค้ดจาก AI local (Ollama, โมเดล `qwen2.5:7b-instruct`) ที่ `ai_advisor.py`
  — รันบนเครื่องเดียวกัน ไม่ส่งโค้ด/ข้อมูลออกอินเทอร์เน็ต ใช้ `/api/chat` + system prompt
  บังคับภาษาไทย + ตรวจจับอักขระจีน (CJK) แล้วขอใหม่อัตโนมัติถ้าหลุดภาษา (แก้บั๊กที่
  โมเดลสลับไปตอบเป็นภาษาจีนปนมา)
- Confetti / matrix-rain background / glow effect ตอนผ่านโจทย์

## หัวข้อสำคัญในโครงร่าง (สำหรับ demo หลัก)

- **3 ตัวชี้วัด** (หัวข้อ 5.1.1 ของเอกสาร): Success Rate, Execution Error Rate,
  First-Attempt Rate — คำนวณจาก Submission Log เท่านั้น เป็นค่า "แนวโน้ม" ไม่ใช่คะแนน
  ความสามารถ สูตร:
  - Success Rate = Passed ÷ ทั้งหมด × 100
  - Execution Error Rate = (Execution Error + Timeout + Security Violation) ÷ ทั้งหมด × 100
  - First-Attempt Rate = โจทย์ที่ผ่านตั้งแต่ครั้งแรก ÷ โจทย์ที่ส่งอย่างน้อย 1 ครั้ง × 100
- **5 สถานะผลตรวจ**: Passed, Wrong Answer, Execution Error, Timeout, Security Violation
- **5 กลุ่ม error_type สำหรับแสดงผล** (ตารางที่ 4): SyntaxError, IndentationError,
  NameError, TypeError, Index/Value Error (รวม IndexError+ValueError) — นอกเหนือจากนี้
  จัดเป็น "Other Exception" ทั้งหมด
- **กฎ AST มีแค่ 3 กฎเท่านั้น** (หัวข้อ 5.2): (1) ตรวจ syntax ก่อนรัน (2) ตรวจโครงสร้าง
  if/for/while/def ตามที่โจทย์กำหนด เป็นคำแนะนำเท่านั้น ไม่ตัดสินผ่าน/ไม่ผ่าน
  (3) ตรวจชื่อตัวแปรตัวอักษรเดียว — **ไม่มีการตรวจความลึก loop/if ซ้อนกัน และไม่มี
  real-time check ขณะพิมพ์** (feedback ต้อง "ทันทีหลังส่งซอร์สโค้ด" เท่านั้น)
- **ไม่มี PDI (Programming Development Index) อีกต่อไป** — เคยมีในโครงร่างฉบับก่อน
  แต่เอกสารฉบับล่าสุดตัดออกหมดแล้ว (ยืนยันด้วยการค้นคำทั้ง 353 paragraph ไม่พบคำว่า PDI
  เลย) Dashboard จึงเหลือแค่ 3 ตัวชี้วัด + กราฟ Error Frequency + 5-way result + ประวัติ
  error ล่าสุด เท่านั้น ไม่มี progress bar/timeline ของ PDI

## สิ่งที่ทำไปในช่วงหลังสุด (เซสชันนี้)

1. **ปรับหน้าตา demo หลักใหม่ทั้งหมด** ให้ไม่ดูเหมือน AI สร้าง — เปลี่ยนชุดสี, ทำ icon
   system เอง (`templates/_icons.html`), แยกสีตามสถานะทั้ง 5 แบบ, โชว์เวลารันโค้ด/สรุป
   test case ในหน้าโจทย์
2. **สร้างโฟลเดอร์ `python_grader_wow`** แยกออกมาเป็น demo โชว์ของ ไม่ยึดขอบเขต
   ตามที่อธิบายด้านบน พร้อมฟีเจอร์ AI advisor + real-time check + nested-if depth +
   เอฟเฟกต์ภาพต่างๆ
3. **ลบ PDI ออกจาก demo หลักทั้งหมด** เพราะโครงร่างฉบับล่าสุดตัดออกไปแล้ว:
   - `grader.py` — ลบ `calc_pdi_timeline()` และ `PDI_WINDOW`
   - `app.py` — ลบ query/ตัวแปร pdi ทั้งหมดใน route `/dashboard`
   - `templates/dashboard.html` — ลบ PDI progress bar + PDI timeline chart (HTML+JS)
   - `static/css/style.css` — ลบ CSS ที่ตายแล้วของ `.pdi-*`/`.level-*`
   - แก้ comment ที่อ้างเลขหัวข้อผิด (`6.2.3` → ที่ถูกคือ `5.1.1` ตรวจจาก heading
     numbering จริงในเอกสาร)
4. **แก้บั๊กจริงที่ทำให้ค่า Dashboard ผิด** (สาเหตุหลักที่ผู้ใช้แจ้งว่า "ค่าในหน้า
   dashboard ผิดหมดเลย"):
   - **บั๊ก 1 — error_logs นับ Timeout/Security Violation ผิด**: โค้ดเดิมบันทึก
     error_logs (และนับเข้า error_type 5 กลุ่ม) ให้ทั้งสถานะ Execution Error, Timeout,
     และ Security Violation — แต่ตามโครงร่าง Timeout/Security Violation เป็น "สถานะการ
     ตัดสินของระบบ ไม่ใช่ Exception Type" แก้ให้บันทึก error_logs เฉพาะตอนสถานะเป็น
     Execution Error เท่านั้น (`grader.py` ฟังก์ชัน `grade_submission`)
   - **บั๊ก 2 — ข้อมูลเก่าในฐานข้อมูลใช้ status คนละชุดกับของใหม่**: พบว่า DB มีข้อมูล
     เก่าก่อนปรับเป็น 5 สถานะ ยังเก็บ `status` แบบตัวพิมพ์เล็ก (`'passed'`, `'failed'`,
     `'error'`) ปนกับของใหม่ (`'Execution Error'` ตัวพิมพ์ใหญ่) ฟังก์ชัน
     `calc_performance_metrics()` เทียบ string แบบ exact-match จึงไม่นับแถวเก่าเป็นทั้ง
     SuccessRate และ ExecutionErrorRate เลย (นับแค่ใน total) ทำให้ % ออกมาต่ำผิดปกติ
     หรือเป็น 0 สำหรับผู้ใช้ที่มีข้อมูลเก่า
     และ `error_logs.error_type` บางแถวเก็บชื่อ exception ดิบๆ (เช่น `ValueError`,
     `EOFError`) ไม่ได้จัดกลุ่มเข้า 5 กลุ่มตามตารางที่ 4 ทำให้กราฟ Error Frequency
     แสดงป้ายชื่อกระจัดกระจายผิดจากที่กำหนด
     **วิธีแก้**: เพิ่มฟังก์ชัน migration ใหม่ `migrate_legacy_status_and_error_type()`
     ใน `database.py` (รันอัตโนมัติทุกครั้งที่ `init_db()` ถูกเรียก) แปลง status เก่า
     (`passed→Passed`, `error→Execution Error`, `failed→Wrong Answer`) และคำนวณ
     error_type ใหม่จาก exception_name ด้วยกฎกลุ่มเดียวกับ `grader.classify_error_type()`
     ทุกแถว — รันแล้วตรวจกับข้อมูลจริง ยืนยันว่าทุก user ได้ค่าถูกต้องแล้ว (เช่น
     user_id=2: SuccessRate 41.5%, ExecutionErrorRate 43.9%)
5. **Restart server** หลังแก้ทุกครั้ง เพราะ Flask debug/reloader ไม่ได้ auto-pick-up
   การแก้ไฟล์เสมอไป (ต้องเช็ค process ที่ bind พอร์ต 5000 จริงๆ ก่อนเชื่อว่า restart
   แล้ว เคยมี process ซ้ำค้างหลายตัวจากการเปิดซ้ำหลายรอบ)

## ไฟล์หลักที่ต้องรู้จักใน `python_grader`

- `app.py` — Flask routes (login, problems, submit, dashboard, error_detail)
- `grader.py` — ตรวจโค้ดจริง (Docker sandbox, AST check, classify error, คำนวณ
  3 ตัวชี้วัด)
- `database.py` — schema + migration ทั้งหมด (MySQL, ตาราง users/problems/test_cases/
  submissions/error_logs/participant_mapping)
- `templates/dashboard.html`, `templates/problem.html` — หน้าแสดงผลหลัก
- `static/css/style.css`, `static/css/style_extra.css` — ธีม/สไตล์

## สถานะปัจจุบัน

Demo หลักรันอยู่ที่ `http://127.0.0.1:5000` ตรวจสอบแล้วว่า:
- ไม่มี PDI เหลืออยู่ในโค้ด/หน้าเว็บเลย (เช็คด้วย grep ทั้งโปรเจกต์)
- สูตร 3 ตัวชี้วัดตรงกับโครงร่างทุกตัวอักษร
- ข้อมูลเก่าในฐานข้อมูลถูก migrate ให้ตรงกับ schema สถานะ/error_type ปัจจุบันแล้ว
- Dashboard render ผ่าน Flask test context จริง ได้ค่าถูกต้องตรงกับที่คำนวณจาก DB ตรงๆ

ยังไม่มีงานค้างที่ทราบ ณ จุดนี้ — ถ้าจะทำต่อ ควรเช็คกับผู้ใช้ว่าต้องการอะไรเพิ่มใน
demo หลัก (ต้องอยู่ในขอบเขตโครงร่าง) หรือ `python_grader_wow` (ไม่ยึดขอบเขต)
