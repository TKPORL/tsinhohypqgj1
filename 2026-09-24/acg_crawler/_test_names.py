import sys, io, os, shutil, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

shutil.copy('data/crawler.db', 'data/_t5.db')
import database
from pathlib import Path
database.DB_PATH = Path('data/_t5.db')
from database import init_db
init_db()
from app import app
client = app.test_client()

print('== 1. 单站筛选导出：文件名应含站名 ==')
r = client.get('/api/export_download?type=mixed&source=' + 'ACG俱乐部')
cd = r.headers.get('Content-Disposition', '')
import urllib.parse
fn = urllib.parse.unquote(cd)
print('  状态:', r.status_code, '文件名:', fn[fn.find('filename*=')+11:][:60])
assert 'ACG俱乐部' in fn, '文件名缺少站名!'

print()
print('== 2. 全部来源导出：文件名 = 全部-PC+安卓 ==')
r = client.get('/api/export_download?type=mixed')
cd = r.headers.get('Content-Disposition', '')
fn = urllib.parse.unquote(cd)
print('  文件名:', fn[fn.find('filename*=')+11:][:60])
assert '全部' in fn

print()
print('== 3. 批次导出：文件名应含批次站点名 ==')
# 批次42是最近的真实任务
r = client.get('/api/export_batch?crawl_id=42&platform=pc_android')
cd = r.headers.get('Content-Disposition', '')
fn = urllib.parse.unquote(cd)
print('  状态:', r.status_code, '文件名:', fn[fn.find('filename*=')+11:][:80])

print()
print('== 4. 单条下载（selected ids）==')
from database import get_posts
p = get_posts(limit=1)[0]
r = client.get('/api/export_download?type=selected&ids=' + str(p['id']))
print('  状态:', r.status_code, '大小:', len(r.data)//1024, 'KB')
assert r.status_code == 200

os.remove('data/_t5.db')
print()
print('=== 文件名+单条下载 验证全部通过 ===')
