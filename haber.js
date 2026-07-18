/* ==========================================================================
   HABER MERKEZİ - FRONTEND JAVASCRIPT
   Backend (haber.py) ile /api/news ve /api/refresh üzerinden konuşur.
   ========================================================================== */

// ============================================================================
// API_BASE — VERCEL İÇİN DİNAMİK ADRES
// ============================================================================
// Vercel'de frontend (haber.html/css/js) ve backend (api/haber.py) AYNI
// domain altında yayınlanır (örn. https://projeniz.vercel.app). Bu yüzden
// API_BASE'i sabit bir adres yerine, sayfanın o an hangi origin'den
// yüklendiğini otomatik algılayan window.location.origin ile tanımlıyoruz.
// Böylece kod; localhost'ta, önizleme (preview) deploy'larında ve
// production'da hiçbir değişiklik gerektirmeden aynı şekilde çalışır.
const API_BASE = window.location.origin;

// Kategori etiketleri (Türkçe görünen isimler)
const CATEGORY_LABELS = {
  genel: "Genel",
  teknoloji: "Teknoloji",
  spor: "Spor",
  ekonomi: "Ekonomi",
  saglik: "Sağlık",
  bilim: "Bilim",
  eglence: "Eğlence",
  politika: "Politika",
};

// Uygulama durumu
const state = {
  search: "",
  category: "tumu",
  language: "tumu",
  sort: "newest",
  newsData: [],
  selectedUuid: null,
};

// DOM referansları
const el = {
  searchInput: document.getElementById("searchInput"),
  languageSelect: document.getElementById("languageSelect"),
  sortSelect: document.getElementById("sortSelect"),
  categoryRow: document.getElementById("categoryRow"),
  newsList: document.getElementById("newsList"),
  newsDetail: document.getElementById("newsDetail"),
  refreshBtn: document.getElementById("refreshBtn"),
  lastUpdated: document.getElementById("lastUpdated"),
  statusBar: document.getElementById("statusBar"),
};

// --------------------------------------------------------------------------
// YARDIMCI FONKSİYONLAR
// --------------------------------------------------------------------------
function showStatus(message, type = "") {
  el.statusBar.textContent = message;
  el.statusBar.className = "status-bar" + (type ? " " + type : "");
  if (message) {
    setTimeout(() => {
      if (el.statusBar.textContent === message) {
        el.statusBar.textContent = "";
        el.statusBar.className = "status-bar";
      }
    }, 4000);
  }
}

function formatTarih(isoString) {
  if (!isoString) return "Tarih bilinmiyor";
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return isoString;
  return d.toLocaleString("tr-TR", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function placeholderImage() {
  return "data:image/svg+xml;utf8," + encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100'>
       <rect width='100%' height='100%' fill='#131722'/>
       <text x='50%' y='50%' fill='#374151' font-size='12' text-anchor='middle' dy='.3em'>Görsel Yok</text>
     </svg>`
  );
}

// --------------------------------------------------------------------------
// API İSTEKLERİ
// --------------------------------------------------------------------------

/**
 * fetch() + güvenli JSON ayrıştırma.
 * Sunucu JSON olmayan bir şey döndürürse (HTML hata sayfası, boş body,
 * fazladan karakter vb.) burada ham metni konsola yazdırır ve
 * anlaşılır bir hata fırlatır. "Unexpected non-whitespace character
 * after JSON..." gibi hataların gerçek sebebini görmek için
 * tarayıcı konsolunu (F12 > Console) kontrol edin.
 */
async function safeFetchJson(url, options) {
  const res = await fetch(url, options);
  const rawText = await res.text();

  let data;
  try {
    data = JSON.parse(rawText);
  } catch (parseErr) {
    console.error(`[JSON HATASI] ${url} adresinden gelen ham cevap:`, rawText);
    throw new Error(
      `Sunucudan geçersiz bir cevap geldi (HTTP ${res.status}). ` +
      `Flask konsolunu ve tarayıcı konsolundaki "JSON HATASI" satırını kontrol edin.`
    );
  }

  if (!res.ok) {
    throw new Error(data.message || `Sunucu hatası (HTTP ${res.status})`);
  }

  return data;
}

async function fetchLastUpdated() {
  try {
    const data = await safeFetchJson(`${API_BASE}/api/last-updated`);
    el.lastUpdated.textContent = data.last_updated || "—";
  } catch (err) {
    console.error(err);
    el.lastUpdated.textContent = "Bilinmiyor";
  }
}

async function fetchNews() {
  const params = new URLSearchParams({
    search: state.search,
    category: state.category,
    language: state.language,
    sort: state.sort,
  });

  el.newsList.innerHTML = `<div class="empty-state" style="min-height:200px;">Haberler yükleniyor...</div>`;

  try {
    const data = await safeFetchJson(`${API_BASE}/api/news?${params.toString()}`);

    if (!data.success) {
      throw new Error(data.message || "Bilinmeyen hata");
    }

    state.newsData = data.data || [];
    el.lastUpdated.textContent = data.last_updated || "—";
    renderNewsList();
  } catch (err) {
    console.error(err);
    el.newsList.innerHTML = `<div class="empty-state" style="min-height:200px;">
      Haberler yüklenemedi. Backend'in çalıştığından emin olun.
    </div>`;
    showStatus("Haberler yüklenirken bir hata oluştu: " + err.message, "error");
  }
}

async function refreshNews() {
  el.refreshBtn.disabled = true;
  el.refreshBtn.classList.add("spinning");
  showStatus("TheNewsAPI'den güncel haberler çekiliyor, lütfen bekleyin...");

  try {
    const data = await safeFetchJson(`${API_BASE}/api/refresh`, { method: "POST" });

    if (!data.success) {
      throw new Error(data.message || "Yenileme başarısız oldu");
    }

    el.lastUpdated.textContent = data.last_updated;
    showStatus(data.message || "Haberler güncellendi.", "success");
    await fetchNews();
  } catch (err) {
    console.error(err);
    showStatus("Yenileme sırasında hata oluştu: " + err.message, "error");
  } finally {
    el.refreshBtn.disabled = false;
    el.refreshBtn.classList.remove("spinning");
  }
}

// --------------------------------------------------------------------------
// RENDER FONKSİYONLARI
// --------------------------------------------------------------------------
function renderNewsList() {
  if (!state.newsData.length) {
    el.newsList.innerHTML = `<div class="empty-state" style="min-height:200px;">
      Bu filtrelerle eşleşen haber bulunamadı.
    </div>`;
    el.newsDetail.innerHTML = defaultEmptyState();
    return;
  }

  el.newsList.innerHTML = state.newsData.map((item) => `
    <div class="news-item ${item.uuid === state.selectedUuid ? "selected" : ""}" data-uuid="${item.uuid}">
      <img src="${item.image_url || placeholderImage()}" onerror="this.src='${placeholderImage()}'" alt="">
      <div class="news-item-body">
        <p class="news-item-title">${escapeHtml(item.title)}</p>
        <div class="news-item-meta">
          <span class="tag tag-${item.category}">${CATEGORY_LABELS[item.category] || item.category}</span>
          <span>${item.language === "tr" ? "TR" : "EN"}</span>
          <span>•</span>
          <span>${formatTarih(item.published_at)}</span>
        </div>
      </div>
    </div>
  `).join("");

  // Tıklama olayları
  document.querySelectorAll(".news-item").forEach((node) => {
    node.addEventListener("click", () => {
      const uuid = node.dataset.uuid;
      state.selectedUuid = uuid;
      renderNewsList();
      const item = state.newsData.find((n) => n.uuid === uuid);
      if (item) renderDetail(item);
    });
  });

  // Eğer daha önce seçili bir haber varsa detayını göster, yoksa boş durum
  if (state.selectedUuid) {
    const item = state.newsData.find((n) => n.uuid === state.selectedUuid);
    if (item) {
      renderDetail(item);
      return;
    }
  }
  el.newsDetail.innerHTML = defaultEmptyState();
}

function renderDetail(item) {
  el.newsDetail.innerHTML = `
    <img class="detail-image" src="${item.image_url || placeholderImage()}" onerror="this.src='${placeholderImage()}'" alt="">
    <div class="detail-meta">
      <span class="tag tag-${item.category}">${CATEGORY_LABELS[item.category] || item.category}</span>
      <span>${item.language === "tr" ? "Türkçe" : "İngilizce"}</span>
      <span>•</span>
      <span>${item.source || "Kaynak bilinmiyor"}</span>
      <span>•</span>
      <span>${formatTarih(item.published_at)}</span>
    </div>
    <h2 class="detail-title">${escapeHtml(item.title)}</h2>
    <p class="detail-desc">${escapeHtml(item.description || item.snippet || "Açıklama bulunamadı.")}</p>
    <a class="detail-link" href="${item.url}" target="_blank" rel="noopener noreferrer">
      Haberin Tamamını Oku
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M7 17 17 7"/><path d="M7 7h10v10"/>
      </svg>
    </a>
  `;
}

function defaultEmptyState() {
  return `
    <div class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M4 4h16v16H4z"/><path d="M4 9h16"/><path d="M9 9v11"/>
      </svg>
      <p>Detayları görmek için soldan bir haber seçin.</p>
    </div>
  `;
}

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// --------------------------------------------------------------------------
// OLAY DİNLEYİCİLERİ (FİLTRELER)
// --------------------------------------------------------------------------
let searchDebounce;
el.searchInput.addEventListener("input", (e) => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    state.search = e.target.value;
    fetchNews();
  }, 350);
});

el.languageSelect.addEventListener("change", (e) => {
  state.language = e.target.value;
  fetchNews();
});

el.sortSelect.addEventListener("change", (e) => {
  state.sort = e.target.value;
  fetchNews();
});

el.categoryRow.addEventListener("click", (e) => {
  const btn = e.target.closest(".pill");
  if (!btn) return;

  el.categoryRow.querySelectorAll(".pill").forEach((p) => p.classList.remove("active"));
  btn.classList.add("active");

  state.category = btn.dataset.category;
  fetchNews();
});

el.refreshBtn.addEventListener("click", refreshNews);

// --------------------------------------------------------------------------
// BAŞLANGIÇ
// --------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  fetchLastUpdated();
  fetchNews();
});