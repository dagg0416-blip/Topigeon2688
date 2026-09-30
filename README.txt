2688 賽鴿分析 Web v3（前後端整合）

本版包含：
- index.html：iPhone/Safari 前端
- server.py：Flask 後端，代替 Safari 對 TOPIGEON 送 POST
- requirements.txt / Procfile：可部署到支援 Python 的雲端服務

本機測試：
1. pip install -r requirements.txt
2. python server.py
3. 瀏覽器開 http://127.0.0.1:8080

正式部署後，手機只需開部署網址。前端 /api/topigeon 會與同網域後端連線，因此沒有 Safari CORS 問題。

固定查詢：QSysid=1606（金溪湖）、QMode=train、QSite/QSiteCode=2688、qsize=1000、QSort=0。
自訓密碼不寫死，使用者若需要才在前端輸入，API 查詢時傳送。

注意：TOPIGEON 為第三方網站，若其表單欄位、驗證、反自動化或服務條款改變，後端可能需要調整。
