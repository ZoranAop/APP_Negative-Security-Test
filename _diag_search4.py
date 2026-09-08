# -*- coding: utf-8 -*-
import sys, time, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'xxai_business_nickname_logo')
from cdp_base import CDPClient, setup_adb_forward
from cdp_helpers import discover_ws

setup_adb_forward()
time.sleep(1)
cdp = CDPClient(discover_ws())
cdp.connect()
cdp.evaluate('location.hash = "#/user/enterprise"')
time.sleep(4)

# Check table structure
r = cdp.evaluate("""
(function(){
  var headers = document.querySelectorAll('.el-table__header-wrapper .cell');
  var h = [];
  headers.forEach(function(c){ h.push(c.innerText.trim()); });
  var rows = document.querySelectorAll('.el-table__body-wrapper .el-table__row');
  var row0 = rows.length > 0 ? rows[0].innerText.substring(0,200) : '';
  return JSON.stringify({headers: h, rowCount: rows.length, row0: row0});
})()
""")
print("Table info:", r)

# Check what API params the search uses - look at network requests by inspecting the input listener
r2 = cdp.evaluate("""
(async function(){
  var m = document.cookie.match(/authorized-token=(.+?)(?:;|$)/);
  if(!m) return "NO_COOKIE";
  var token = JSON.parse(decodeURIComponent(m[1])).accessToken;
  // Try searching by username field
  var resp = await fetch("https://merchant-api.xxai.com/user/pool-users?username=u_axgr20bc&page=1&page_size=5",{headers:{"Authorization":"Bearer "+token}});
  var data = await resp.json();
  return JSON.stringify({code:data.code,total:data.data?data.data.total:0,listLen:data.data&&data.data.list?data.data.list.length:0});
})()
""")
print("Search by username:", r2)

# Also try the nickname as exact match
r3 = cdp.evaluate("""
(async function(){
  var m = document.cookie.match(/authorized-token=(.+?)(?:;|$)/);
  if(!m) return "NO_COOKIE";
  var token = JSON.parse(decodeURIComponent(m[1])).accessToken;
  var resp = await fetch("https://merchant-api.xxai.com/user/pool-users?nickname=AspenWind&page=1&page_size=5",{headers:{"Authorization":"Bearer "+token}});
  var data = await resp.json();
  return JSON.stringify({code:data.code,total:data.data?data.data.total:0,listLen:data.data&&data.data.list?data.data.list.length:0});
})()
""")
print("Search by old nickname:", r3)

cdp.close()
