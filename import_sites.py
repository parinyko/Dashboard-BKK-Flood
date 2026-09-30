import os, sqlite3, pandas as pd
BASE_DIR=os.path.dirname(os.path.abspath(__file__))
XLSX=os.path.join(BASE_DIR,'data','Location_Site.xlsx')
DB=os.path.join(BASE_DIR,'data','sites.db')
os.makedirs(os.path.dirname(DB),exist_ok=True)
df=pd.read_excel(XLSX)
df=df.rename(columns={
    'SITE_CODE':'site_code','LOCATION_NAME_EN':'location_name','TUMBOL':'tumbol',
    'AMPHUR':'amphur','PROVINCE':'province','LATITUDE_RF':'latitude','LONGITUDE_RF':'longitude'
})[['site_code','location_name','tumbol','amphur','province','latitude','longitude']]
for c in ['site_code','location_name','tumbol','amphur','province']:
    df[c]=df[c].fillna('').astype(str).str.strip()
for c in ['latitude','longitude']:
    df[c]=pd.to_numeric(df[c],errors='coerce')
ALLOWED_PROVINCES = ['กรุงเทพมหานคร', 'ปทุมธานี', 'นนทบุรี', 'สมุทรปราการ']
df=df[df['province'].isin(ALLOWED_PROVINCES)].copy()
df=df.dropna(subset=['latitude','longitude'])
conn=sqlite3.connect(DB)
df.to_sql('sites',conn,if_exists='replace',index=False)
conn.execute('CREATE INDEX IF NOT EXISTS idx_sites_lat_lon ON sites(latitude, longitude)')
conn.execute('CREATE INDEX IF NOT EXISTS idx_sites_code ON sites(site_code)')
conn.execute('CREATE INDEX IF NOT EXISTS idx_sites_province ON sites(province)')
conn.commit(); conn.close()
print(f'Imported {len(df):,} sites -> {DB}')
