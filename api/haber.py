# -*- coding: utf-8 -*-
"""
haber.py
--------
Flask tabanlı haber sayfası backend'i.
- TheNewsAPI'den haber çeker ve yerel SQLite veritabanında saklar (haber_cache.db).
- Kullanıcılar sayfayı her açtığında API'ye istek atılmaz; veriler DB'den okunur.
- "Haberleri Yenile" butonuna basıldığında /api/refresh çağrılır ve DB güncellenir.
- /api/news uç noktası arama, kategori, dil ve sıralama filtrelerini destekler.

Çalıştırmak için:
    pip install flask requests
    python haber.py
"""

import os
import sqlite3
import requests
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory, g

# --------------------------------------------------------------------------
# AYARLAR
# --------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "haber_cache.db")

# TheNewsAPI ayarları
THENEWSAPI_TOKEN = "ctJKHQ8zto5MBCk7tbqH5uy3tBZLuEg0RhsoMu4q"
THENEWSAPI_URL = "https://api.thenewsapi.com/v1/news/top"

# Frontend'de gösterilecek / API'ye gönderilecek kategoriler
CATEGORY_MAP = {
    "genel": "general",
    "teknoloji": "tech",
    "spor": "sports",
    "ekonomi": "business",
    "saglik": "health",
    "bilim": "science",
    "eglence": "entertainment",
    "politika": "politics",
}

# Yenileme sırasında hangi dil + kategori kombinasyonlarının çekileceği
LANGUAGES = ["tr", "en"]

app = Flask(__name__, static_folder=None)

# --------------------------------------------------------------------------
# CORS (Cross-Origin Resource Sharing)
# --------------------------------------------------------------------------
# Bu backend'i mevcut web sitenize entegre ederken, haberler.html'i
# BAŞKA bir sunucudan (farklı domain/port) sunuyorsanız, tarayıcı
# güvenlik politikaları gereği /api/... isteklerini engelleyebilir
# ya da 404/CORS hatası alırsınız. Aşağıdaki blok, API'nin farklı bir
# origin'den de çağrılabilmesini sağlar. Üretimde "*" yerine kendi
# site adresinizi yazmanız önerilir (örn. "https://siteniz.com").
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def cors_preflight(_any):
    """Tarayıcının CORS ön kontrol (preflight) isteklerine boş 200 döner."""
    return "", 200

# Aynı anda birden fazla /api/refresh isteğinin SQLite'ı kilitlemesini
# (ve bu yüzden yarım/bozuk cevap dönmesini) engellemek için basit bir kilit.
_refresh_in_progress = False


# --------------------------------------------------------------------------
# VERİTABANI YARDIMCI FONKSİYONLARI
# --------------------------------------------------------------------------
def get_db():
    """İstek bazlı SQLite bağlantısı döndürür."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Uygulama ilk çalıştığında tabloları oluşturur."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE,
            title TEXT,
            description TEXT,
            snippet TEXT,
            url TEXT,
            image_url TEXT,
            source TEXT,
            category TEXT,
            language TEXT,
            published_at TEXT,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()


def set_meta(key, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_meta(key):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else None


# --------------------------------------------------------------------------
# THE NEWS API'DEN VERİ ÇEKME
# --------------------------------------------------------------------------
def fetch_from_thenewsapi(language, category_tr, category_en):
    """Belirli bir dil/kategori için TheNewsAPI'den haber çeker."""
    params = {
        "api_token": THENEWSAPI_TOKEN,
        "language": language,
        "categories": category_en,
        "limit": 15,
    }
    try:
        resp = requests.get(THENEWSAPI_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except requests.RequestException as e:
        print(f"[HATA] TheNewsAPI isteği basarisiz ({language}/{category_en}): {e}")
        return []


def refresh_news_cache():
    """Tüm dil/kategori kombinasyonları için haberleri çekip DB'ye yazar."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    total_inserted = 0

    for lang in LANGUAGES:
        for category_tr, category_en in CATEGORY_MAP.items():
            articles = fetch_from_thenewsapi(lang, category_tr, category_en)
            for art in articles:
                uuid = art.get("uuid")
                if not uuid:
                    continue
                cur.execute(
                    """
                    INSERT INTO news
                        (uuid, title, description, snippet, url, image_url,
                         source, category, language, published_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(uuid) DO UPDATE SET
                        title=excluded.title,
                        description=excluded.description,
                        snippet=excluded.snippet,
                        url=excluded.url,
                        image_url=excluded.image_url,
                        source=excluded.source,
                        category=excluded.category,
                        language=excluded.language,
                        published_at=excluded.published_at
                    """,
                    (
                        uuid,
                        art.get("title", ""),
                        art.get("description", ""),
                        art.get("snippet", ""),
                        art.get("url", ""),
                        art.get("image_url", ""),
                        (art.get("source") or ""),
                        category_tr,
                        lang,
                        art.get("published_at", ""),
                        datetime.now().isoformat(),
                    ),
                )
                total_inserted += 1

    conn.commit()
    conn.close()

    now_str = datetime.now().strftime("%d.%m.%Y - %H:%M")
    set_meta("last_updated", now_str)
    return total_inserted, now_str


# --------------------------------------------------------------------------
# API UÇ NOKTALARI
# --------------------------------------------------------------------------
@app.route("/api/news", methods=["GET"])
def get_news():
    """
    Veritabanından filtrelenmiş haberleri döndürür.
    Query parametreleri:
        search    -> başlık/içerikte anahtar kelime
        category  -> genel, teknoloji, spor, ekonomi, saglik, bilim, eglence, politika, tumu
        language  -> tr, en, tumu
        sort      -> newest, oldest
    """
    search = request.args.get("search", "").strip().lower()
    category = request.args.get("category", "tumu")
    language = request.args.get("language", "tumu")
    sort = request.args.get("sort", "newest")

    query = "SELECT * FROM news WHERE 1=1"
    params = []

    if search:
        query += " AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ?)"
        like_term = f"%{search}%"
        params.extend([like_term, like_term])

    if category and category != "tumu":
        query += " AND category = ?"
        params.append(category)

    if language and language != "tumu":
        query += " AND language = ?"
        params.append(language)

    query += " ORDER BY published_at " + ("ASC" if sort == "oldest" else "DESC")

    db = get_db()
    rows = db.execute(query, params).fetchall()
    news_list = [dict(row) for row in rows]

    return jsonify({
        "success": True,
        "count": len(news_list),
        "last_updated": get_meta("last_updated") or "Henüz güncellenmedi",
        "data": news_list,
    })


@app.route("/api/refresh", methods=["POST"])
def refresh_news():
    """TheNewsAPI'den yeni veri çekip veritabanını günceller."""
    global _refresh_in_progress

    if _refresh_in_progress:
        return jsonify({
            "success": False,
            "message": "Yenileme zaten devam ediyor, lütfen bekleyin.",
        }), 429

    _refresh_in_progress = True
    try:
        count, last_updated = refresh_news_cache()
        return jsonify({
            "success": True,
            "message": f"{count} haber güncellendi.",
            "last_updated": last_updated,
        })
    except Exception as e:
        # Hatanın tamamını Flask konsoluna da yazdır (tarayıcıda görünmeyen
        # traceback'i terminalden takip edebilmek için).
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        _refresh_in_progress = False


@app.route("/api/last-updated", methods=["GET"])
def last_updated():
    return jsonify({
        "success": True,
        "last_updated": get_meta("last_updated") or "Henüz güncellenmedi",
    })


# --------------------------------------------------------------------------
# STATİK DOSYA SUNUMU (Frontend)
# --------------------------------------------------------------------------
@app.route("/")
@app.route("/haberler.html")
def haberler_sayfasi():
    return send_from_directory(BASE_DIR, "haberler.html")


@app.route("/haber.css")
def css_dosyasi():
    return send_from_directory(BASE_DIR, "haber.css")


@app.route("/haber.js")
def js_dosyasi():
    return send_from_directory(BASE_DIR, "haber.js")


@app.route("/index.html")
def ana_sayfa():
    """
    Mevcut web sitenizin ana sayfası (index.html) bu klasörde de bulunuyorsa
    servis eder. Kendi index.html dosyanızı bu dizine kopyalamanız yeterli;
    aksi halde bu route'u kendi site yapınıza göre yönlendirin.
    """
    if os.path.exists(os.path.join(BASE_DIR, "index.html")):
        return send_from_directory(BASE_DIR, "index.html")
    return ("index.html bulunamadı. Lütfen kendi ana sayfanızı bu klasöre "
            "ekleyin veya /index.html route'unu kendi sitenize göre "
            "yönlendirin."), 404


# --------------------------------------------------------------------------
# UYGULAMAYI BAŞLAT
# --------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    print(f"[BILGI] Veritabani hazir: {DB_PATH}")
    print("[BILGI] Kayitli API rotalari:")
    for rule in app.url_map.iter_rules():
        if str(rule).startswith("/api"):
            print(f"         -> {rule}")
    print("[BILGI] Sunucu http://127.0.0.1:5000 adresinde calisiyor...")
    print("[UYARI] haberler.html sayfasini FARKLI bir sunucudan aciyorsaniz,")
    print("        haber.js icindeki API_BASE degiskenini bu adrese esitleyin.")
    print("        Ornek: const API_BASE = \"http://127.0.0.1:5000\";")
    app.run(debug=True, port=5000)
