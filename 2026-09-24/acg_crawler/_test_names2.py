import sys, io, os, shutil, urllib.parse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

shutil.copy('data/crawler.db', 'data/_t6.db')
import database
from pathlib import Path
database.DB_PATH = Path('data/_t6.db')
from database import init_db, get_posts
init_db()
from app import app
client = app.test_client()

def fname(r):
    cd = r.headers.get('Content-Disposition', '')
    if 'filename*=' in cd:
        return urllib.parse.unquote(cd.split("filename*=")[1].split("''", 1)[1])
    return cd

print('== 1. 单站导出文件名 ==')
r = client.get('/api/export_download?type=mixed&source=ACG俱乐部')
fn = fname(r)
print('  ', r.status_code, fn)
assert 'ACG俱乐部' in fn and fn.startswith('PC+安卓下载-ACG俱乐部-')

print('== 2. 全来源导出文件名 ==')
r = client.get('/api/export_download?type=pc')
fn = fname(r)
print('  ', r.status_code, fn)
assert '全部来源' in fn

print('== 3. 批次导出文件名（含站名）==')
r = client.get('/api/export_batch?crawl_id=42&platform=pc_android')
fn = fname(r)
print('  ', r.status_code, fn)

print('== 4. 单条下载 ==')
p = get_posts(limit=1)[0]
r = client.get('/api/export_download?type=selected&ids=' + str(p['id']))
print('  ', r.status_code, len(r.data)//1024, 'KB', fname(r))
assert r.status_code == 200 and len(r.data) > 1000

os.remove('data/_t6.db')
print()
print('=== 全部验证通过 ===')
