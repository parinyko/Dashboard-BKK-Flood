# FloodBoard + Site Base Operations Dashboard

Dashboard แบบเต็มจอสำหรับติดตาม Site Base 55,569 จุด โดยใช้ Flask + SQLite + Leaflet และอ้างอิงชั้นถนนน้ำท่วมจาก FloodBoard Open Data

## ฟังก์ชัน
- แผนที่เต็มจอ + Street/Satellite
- Site Base 55,569 จุด
- Marker สีตามสถานะน้ำใกล้เคียง
  - แดง: น้ำลึก/เสี่ยง >= 70 cm
  - ส้ม: 20–69 cm
  - เหลือง: ระดับต่ำ/น้ำลด
  - เขียว: ไม่พบถนนน้ำท่วมใกล้เคียง
- ค้นหา Site แล้ว Zoom ไปยังจุดทันที
- Filter จังหวัด / อำเภอ
- Dashboard สรุปจำนวน Site ทั้งหมด, ใกล้พื้นที่น้ำท่วม, ระดับรุนแรง/ปานกลาง/ต่ำ และ Site ที่ไม่พบถนนน้ำท่วมใกล้เคียง
- ตาราง Site
- Export รายงานเป็น Excel ตามตัวกรอง พร้อมสถานะน้ำและระยะจากถนนที่ FloodBoard รายงาน
- FloodBoard GeoJSON cache 60 วินาที

## ติดตั้ง
```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
เปิด `http://127.0.0.1:5000`

## หมายเหตุเรื่องสถานะน้ำ
สถานะของ Site เป็น **operational proximity indicator** โดยจับคู่พิกัด Site กับถนนที่ FloodBoard รายงานในรัศมีประมาณ 100–170 เมตร ไม่ใช่แบบจำลองพื้นที่น้ำท่วมเชิงไฮดรอลิก ดังนั้นควรใช้เป็นตัวช่วยคัดกรองและตรวจสอบกับข้อมูลภาคสนามอีกครั้ง

FloodBoard ระบุว่า Open Data ประกอบด้วย `roads.geojson`, `reports.csv`, `stats.json` และ `feed.json` และข้อมูลอาจไม่ครบ ล่าช้า หรือผิดพลาดได้
