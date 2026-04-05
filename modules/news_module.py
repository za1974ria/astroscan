
import requests, time
_cache={"ts":0,"data":[]}
def get_live_news():
    if time.time()-_cache["ts"]<300 and _cache["data"]: return _cache["data"]
    try:
        r=requests.get("https://api.spaceflightnewsapi.net/v4/articles/?limit=20&ordering=-published_at",timeout=8,headers={"User-Agent":"AstroScan/2"})
        arts=[{"title":a["title"],"summary":a["summary"],"url":a["url"],"image":a.get("image_url",""),"source":a.get("news_site",""),"published":a.get("published_at","")} for a in r.json().get("results",[])]
        _cache.update({"ts":time.time(),"data":arts})
        return arts
    except: return []
def get_news(): return get_live_news()
