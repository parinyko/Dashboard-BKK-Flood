# Bangkok Metropolitan Flood Analyzer — Python Web

เว็บ Python/Flask สำหรับ Job Monitor ของ Bangkok Metropolitan Flood Analyzer

## ฟังก์ชัน
- Filter: Sub System / Zone / Priority
- Filter เพิ่ม: Status / Province / Search
- กรองหลายเงื่อนไขพร้อมกัน
- Dashboard counters
- Job Map สำหรับงานที่มีพิกัด
- เปิดรายละเอียดและ Job Analysis
- Upload Job Monitor Excel เพื่อแทนที่ snapshot
- โครงหน้า Flood Analysis สำหรับต่อ Google/Flood Bangkok/Traffy

## วิธีรันบน Windows

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

เปิด http://127.0.0.1:5000

## หมายเหตุ
แผนที่เวอร์ชันนี้ใช้ Leaflet + OpenStreetMap เพื่อให้เริ่มใช้งานได้โดยไม่ต้องมี Google API key
และเตรียมจุดเชื่อมสำหรับ Google Maps Platform ในขั้นถัดไป
