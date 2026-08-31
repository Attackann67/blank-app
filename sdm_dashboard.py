# -*- coding: utf-8 -*-
"""
SDM Kontrol Dashboard'u
=======================
Banka Bilgileri Değişikliği (SDM) taleplerinde, SDM ekran görüntüsündeki
"Yeni Veriler" ile tedarikçinin gönderdiği belgeleri (banka deklarasyonu,
tedarikçi bilgi formu, hesap cüzdanı, vergi levhası) karşılaştırır ve
farkları / riskleri yakalar.

Çalıştırma:
    streamlit run sdm_dashboard.py

Girdi:
  - SDM ekran görüntüleri (PNG/JPG)  → OCR ile alanlar çıkarılır
  - Tedarikçi PDF'leri               → metin katmanı varsa direkt,
                                       yoksa OCR (RapidOCR) ile okunur
  - İsteğe bağlı manuel SDM alanları (OCR'ı doğrulamak/düzeltmek için)

Kontroller:
  1. IBAN yapısal doğrulama (mod-97) + banka kodu ↔ banka adı
  2. SDM'deki yeni IBAN'ın belgelerde geçip geçmediği (kaç belgede?)
  3. Hesap no ↔ IBAN tutarlılığı (hesap no IBAN'ın içinde mi?)
  4. Banka anahtarı (banka + şube kodu) ↔ IBAN tutarlılığı
  5. Para birimi tutarlılığı
  6. Vergi numarası eşleşmesi
  7. Unvan (hesap sahibi) benzerliği
"""

import io
import re
import unicodedata
from difflib import SequenceMatcher

import pandas as pd
import streamlit as st

# ----------------------------------------------------------------------------
# Sabitler
# ----------------------------------------------------------------------------

# TR IBAN'daki 5 haneli banka kodu → banka adı
TR_BANKA_KODLARI = {
    "00001": "T.C. Merkez Bankası",
    "00010": "Ziraat Bankası",
    "00012": "Halkbank",
    "00015": "VakıfBank",
    "00032": "TEB",
    "00046": "Akbank",
    "00059": "Şekerbank",
    "00062": "Garanti BBVA",
    "00064": "İş Bankası",
    "00067": "Yapı Kredi",
    "00099": "ING",
    "00103": "Fibabanka",
    "00111": "QNB",
    "00123": "HSBC",
    "00124": "Alternatif Bank",
    "00134": "DenizBank",
    "00146": "Odeabank",
    "00203": "Albaraka Türk",
    "00205": "Kuveyt Türk",
    "00206": "Türkiye Finans",
    "00209": "Ziraat Katılım",
    "00210": "Vakıf Katılım",
    "00211": "Emlak Katılım",
}

PARA_BIRIMLERI = ["USD", "EUR", "GBP", "TRY", "TL", "CHF", "JPY", "CNY", "SEK"]

# ----------------------------------------------------------------------------
# Yardımcılar: normalizasyon
# ----------------------------------------------------------------------------


def normalize_text(s: str) -> str:
    """Türkçe karakterleri sadeleştirip büyük harfe çevirir (karşılaştırma için)."""
    s = s.upper().replace("İ", "I").replace("Ş", "S").replace("Ğ", "G")
    s = s.replace("Ü", "U").replace("Ö", "O").replace("Ç", "C").replace("Â", "A")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def fix_ocr_digits(s: str) -> str:
    """OCR'ın rakam yerine okuduğu harfleri düzeltir (O→0, I/l→1, S→5, B→8)."""
    return s.translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "İ": "1"}))


def clean_iban(s: str) -> str:
    s = re.sub(r"[\s\-\.·]", "", s.upper())
    if s.startswith("TR"):
        s = "TR" + fix_ocr_digits(s[2:])
    return s


# ----------------------------------------------------------------------------
# IBAN doğrulama / ayrıştırma
# ----------------------------------------------------------------------------


def iban_mod97_gecerli(iban: str) -> bool:
    iban = clean_iban(iban)
    if not re.fullmatch(r"TR\d{24}", iban):
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(int(c, 36)) for c in rearranged)  # A=10 ... Z=35
    return int(numeric) % 97 == 1


def iban_parcala(iban: str) -> dict:
    """TR IBAN: TR + 2 kontrol + 5 banka kodu + 1 rezerv + 16 hesap alanı."""
    iban = clean_iban(iban)
    if not re.fullmatch(r"TR\d{24}", iban):
        return {}
    banka_kodu = iban[4:9]
    return {
        "iban": iban,
        "kontrol": iban[2:4],
        "banka_kodu": banka_kodu,
        "banka_adi": TR_BANKA_KODLARI.get(banka_kodu, "Bilinmiyor"),
        "hesap_alani": iban[10:],
        "gecerli": iban_mod97_gecerli(iban),
    }


def iban_bicimle(iban: str) -> str:
    iban = clean_iban(iban)
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


# ----------------------------------------------------------------------------
# Metinden alan çıkarma
# ----------------------------------------------------------------------------

# OCR araya boşluk/tire koyabilir; O/I gibi harf karışmalarına da izin ver
_IBAN_RE = re.compile(r"TR[\s\-\.]?((?:[0-9OIl][\s\-\.]?){24})")


def ibanlari_bul(text: str) -> list:
    """Metindeki tüm TR IBAN'ları normalize ederek döndürür (sıra korunur)."""
    bulunan = []
    for m in _IBAN_RE.finditer(fix_ocr_digits(text)):
        iban = clean_iban("TR" + m.group(1))
        if len(iban) == 26 and iban not in bulunan:
            bulunan.append(iban)
    return bulunan


def vergi_no_bul(text: str) -> list:
    """VKN adayları: 'vergi' kelimesine yakın 10 haneli sayılar; yoksa tüm 10 haneliler."""
    t = fix_ocr_digits(text)
    yakin = []
    for m in re.finditer(r"(?i)(verg|tax|vkn|v\.?d\.?)[^\n]{0,80}?(\d[\d\s]{8,14}\d)", t):
        aday = re.sub(r"\s", "", m.group(2))
        if len(aday) == 10 and aday not in yakin:
            yakin.append(aday)
    if yakin:
        return yakin
    return list(dict.fromkeys(re.findall(r"(?<!\d)(\d{10})(?!\d)", t)))


def talep_no_bul(text: str):
    m = re.search(r"(?i)talep\s*no\s*[:\.]?\s*(\d{3,10})", text)
    return m.group(1) if m else None


def para_birimleri_bul(text: str) -> list:
    t = normalize_text(text)
    return [pb for pb in PARA_BIRIMLERI if re.search(rf"(?<![A-Z]){pb}(?![A-Z])", t)]


def banka_anahtari_bul(text: str) -> list:
    """SDM 'Banka anahtarı' biçimi: 062-0121 gibi (banka kodu - şube kodu)."""
    return list(dict.fromkeys(re.findall(r"(?<!\d)(\d{3}-\d{4})(?!\d)", fix_ocr_digits(text))))


def hesap_no_bul(text: str, ibanlar: list) -> list:
    """5-9 haneli hesap no adayları; IBAN içinde geçenler öncelikli."""
    t = fix_ocr_digits(text)
    adaylar = list(dict.fromkeys(re.findall(r"(?<!\d)(\d{5,9})(?!\d)", t)))
    iban_ici = [a for a in adaylar if any(a in i[10:] for i in ibanlar)]
    return iban_ici or adaylar[:10]


def unvan_bul(text: str) -> list:
    """Hesap sahibi / ticaret unvanı adayları (A.Ş., LTD vb. içeren satırlar)."""
    adaylar = []
    for satir in text.splitlines():
        n = normalize_text(satir)
        if re.search(r"\b(A\.?S\.?|LTD|SAN|TIC|ANONIM|SIRKETI)\b", n) and len(n) > 12:
            n = re.sub(r"^(HESAP SAHIBI|ACCOUNT HOLDER|TICARET UNVANI)\s*[:\.]?\s*", "", n)
            if n not in adaylar:
                adaylar.append(n)
    return adaylar


def sdm_bolumle(text: str) -> tuple:
    """SDM ekranını 'Güncel Veriler' / 'Yeni Veriler' bölümlerine ayırır.

    Yeni Veriler'de olup Güncel Veriler'de olmayan IBAN'lar 'yeni eklenen'
    kabul edilir — belge teyidi asıl onlar için zorunludur.
    """
    n = normalize_text(text.replace("\n", " ⏎ "))
    m_yeni = re.search(r"YEN[I1]\s*VER[I1]LER", n)
    if not m_yeni:
        ibanlar = ibanlari_bul(text)
        return [], ibanlar  # bölüm yoksa hepsini yeni say
    guncel_kisim = n[: m_yeni.start()]
    yeni_kisim = n[m_yeni.start() :]
    guncel = ibanlari_bul(guncel_kisim)
    yeni = [i for i in ibanlari_bul(yeni_kisim) if i not in guncel]
    return guncel, yeni


def alanlari_cikar(text: str, kaynak: str) -> dict:
    ibanlar = ibanlari_bul(text)
    return {
        "kaynak": kaynak,
        "ibanlar": ibanlar,
        "vergi_no": vergi_no_bul(text),
        "talep_no": talep_no_bul(text),
        "para_birimleri": para_birimleri_bul(text),
        "banka_anahtarlari": banka_anahtari_bul(text),
        "hesap_no": hesap_no_bul(text, ibanlar),
        "unvanlar": unvan_bul(text),
        "metin": text,
    }


# ----------------------------------------------------------------------------
# Dosya okuma (PDF metin katmanı → yoksa OCR)
# ----------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _ocr_motoru():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _pixmap_to_np(pix):
    import numpy as np

    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)


@st.cache_data(show_spinner=False, max_entries=32)
def pdf_metni_oku(dosya_adi: str, veri: bytes) -> str:
    """Önce gömülü metni dener; sayfa metinsizse OCR uygular."""
    import pymupdf

    ocr = None
    parcalar = []
    with pymupdf.open(stream=veri, filetype="pdf") as doc:
        for page in doc:
            t = page.get_text().strip()
            if len(t) < 30:  # taranmış sayfa → OCR
                if ocr is None:
                    ocr = _ocr_motoru()
                pix = page.get_pixmap(dpi=220)
                res, _ = ocr(_pixmap_to_np(pix))
                t = "\n".join(r[1] for r in res) if res else ""
            parcalar.append(t)
    return "\n".join(parcalar)


@st.cache_data(show_spinner=False, max_entries=32)
def resim_metni_oku(dosya_adi: str, veri: bytes) -> str:
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(veri)).convert("RGB")
    res, _ = _ocr_motoru()(np.array(img))
    return "\n".join(r[1] for r in res) if res else ""


# ----------------------------------------------------------------------------
# Karşılaştırma mantığı
# ----------------------------------------------------------------------------

OK, WARN, FAIL = "✅", "⚠️", "❌"


def unvan_benzerligi(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def karsilastir(sdm: dict, belgeler: list) -> list:
    """SDM alanları ↔ belge alanları kontrol listesi üretir."""
    bulgular = []

    def ekle(durum, kontrol, detay):
        bulgular.append({"Durum": durum, "Kontrol": kontrol, "Detay": detay})

    guncel_set = set(sdm.get("guncel_ibanlar", []))

    # --- 1) SDM'deki IBAN'lar ---
    if not sdm["ibanlar"]:
        ekle(WARN, "SDM IBAN", "SDM tarafında IBAN bulunamadı (ekran görüntüsü yükleyin veya manuel girin).")
    for iban in sdm["ibanlar"]:
        p = iban_parcala(iban)
        mevcut = iban in guncel_set
        etiket = "mevcut kayıt" if mevcut else "YENİ eklenen"
        # yapısal doğrulama
        if p.get("gecerli"):
            ekle(OK, "IBAN mod-97", f"{iban_bicimle(iban)} ({etiket}) yapısal olarak geçerli ({p['banka_adi']}).")
        else:
            ekle(FAIL, "IBAN mod-97", f"{iban_bicimle(iban)} GEÇERSİZ — kontrol basamağı tutmuyor (OCR hatası ya da sahte IBAN olabilir).")
        # belgelerde geçiyor mu?
        gecen = [b["kaynak"] for b in belgeler if iban in b["ibanlar"]]
        if gecen:
            durum = OK if len(gecen) >= 2 else WARN
            ekle(durum, "IBAN belge teyidi", f"{iban_bicimle(iban)} ({etiket}) şu belgelerde geçiyor: {', '.join(gecen)}" + ("" if len(gecen) >= 2 else " (yalnızca TEK belgede — ikinci kaynakla teyit edin)."))
        elif mevcut:
            ekle(WARN, "IBAN belge teyidi", f"{iban_bicimle(iban)} mevcut (güncel) kayıt — belgelerde geçmiyor, değişiklik kapsamında değilse sorun değil.")
        else:
            ekle(FAIL, "IBAN belge teyidi", f"{iban_bicimle(iban)} YENİ eklenen IBAN HİÇBİR belgede bulunamadı!")
        # hesap no tutarlılığı
        for hn in sdm["hesap_no"]:
            if hn in iban[10:]:
                ekle(OK, "Hesap no ↔ IBAN", f"Hesap no {hn}, IBAN'ın hesap alanında geçiyor.")
                break
        # banka anahtarı tutarlılığı (062-0121 → banka 062 ↔ IBAN 00062, şube 0121 ↔ hesap alanı)
        for ba in sdm["banka_anahtarlari"]:
            banka, sube = ba.split("-")
            banka_uyum = p.get("banka_kodu", "").endswith(banka.lstrip("0") or "0")
            sube_uyum = sube in iban[10:]
            if banka_uyum and sube_uyum:
                ekle(OK, "Banka anahtarı ↔ IBAN", f"Banka anahtarı {ba} ({p['banka_adi']}) IBAN ile tutarlı.")
            elif not banka_uyum:
                ekle(FAIL, "Banka anahtarı ↔ IBAN", f"Banka anahtarı {ba} IBAN'daki banka kodu {p.get('banka_kodu')} ile UYUŞMUYOR.")
            else:
                ekle(WARN, "Banka anahtarı ↔ IBAN", f"Şube kodu {sube} IBAN hesap alanında görünmüyor — şube kontrolü yapın.")

    # --- 2) Belgelerde olup SDM'de olmayan IBAN'lar ---
    sdm_iban_set = set(sdm["ibanlar"])
    for b in belgeler:
        fark = [i for i in b["ibanlar"] if i not in sdm_iban_set]
        if fark:
            ekle(WARN, "Belgede ek IBAN", f"{b['kaynak']}: SDM'de olmayan IBAN(lar): " + ", ".join(iban_bicimle(i) for i in fark) + " (farklı para birimi hesabı olabilir).")

    # --- 3) Para birimi ---
    if sdm["para_birimleri"]:
        belge_pb = {pb for b in belgeler for pb in b["para_birimleri"]}
        for pb in sdm["para_birimleri"]:
            pbn = "TRY" if pb == "TL" else pb
            esles = pb in belge_pb or pbn in belge_pb or ("TL" in belge_pb and pb == "TRY")
            ekle(OK if esles else WARN, "Para birimi", f"SDM para birimi {pb}" + (" belgelerde de geçiyor." if esles else " belgelerde görünmüyor!"))

    # --- 4) Vergi numarası ---
    belge_vkn = {v for b in belgeler for v in b["vergi_no"]}
    if sdm["vergi_no"] and belge_vkn:
        for v in sdm["vergi_no"]:
            ekle(OK if v in belge_vkn else FAIL, "Vergi no", f"VKN {v}" + (" belgelerle eşleşiyor." if v in belge_vkn else f" belgelerdeki VKN'lerle ({', '.join(sorted(belge_vkn))}) EŞLEŞMİYOR."))
    elif belge_vkn:
        if len(belge_vkn) == 1:
            ekle(OK, "Vergi no", f"Belgelerde tek tutarlı VKN: {belge_vkn.pop()}. (SDM tarafında VKN okunamadı.)")
        else:
            ekle(WARN, "Vergi no", f"Belgelerde birden fazla VKN adayı: {', '.join(sorted(belge_vkn))} — kontrol edin.")

    # --- 5) Unvan / hesap sahibi ---
    if sdm["unvanlar"]:
        for u in sdm["unvanlar"][:2]:
            en_iyi, skor = None, 0.0
            for b in belgeler:
                for bu in b["unvanlar"]:
                    s = unvan_benzerligi(u, bu)
                    if s > skor:
                        en_iyi, skor = (bu, b["kaynak"]), s
            if en_iyi and skor >= 0.75:
                ekle(OK, "Unvan", f"'{u}' ↔ '{en_iyi[0]}' ({en_iyi[1]}) benzerlik %{skor*100:.0f}.")
            elif en_iyi:
                ekle(FAIL, "Unvan", f"'{u}' belgelerdeki unvanlarla eşleşmiyor (en yakın: '{en_iyi[0]}', %{skor*100:.0f}).")
    else:
        belge_unvan = [u for b in belgeler for u in b["unvanlar"]]
        if belge_unvan:
            ekle(WARN, "Unvan", f"SDM tarafında unvan okunamadı. Belgelerdeki hesap sahibi: {belge_unvan[0]}")

    return bulgular


# ----------------------------------------------------------------------------
# Arayüz
# ----------------------------------------------------------------------------

st.set_page_config(page_title="SDM Kontrol Dashboard", page_icon="🏦", layout="wide")

st.title("🏦 SDM Kontrol Dashboard'u")
st.caption(
    "Banka Bilgileri Değişikliği taleplerinde SDM ekranındaki verilerle tedarikçi "
    "belgelerini (banka deklarasyonu, tedarikçi formu, hesap cüzdanı, vergi levhası) "
    "karşılaştırır; IBAN, hesap no, banka anahtarı, para birimi, VKN ve unvan farklarını yakalar."
)

sol, sag = st.columns(2)

with sol:
    st.subheader("1️⃣ SDM ekran görüntüleri")
    ss_dosyalar = st.file_uploader(
        "SDM 'Banka Bilgileri Değişikliği' ekran görüntüleri (PNG/JPG)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )
    with st.expander("✍️ Manuel SDM verisi (OCR yerine / OCR'a ek)"):
        m_iban = st.text_input("Yeni IBAN", placeholder="TR17 0006 2000 1210 0009 0818 23")
        m_hesap = st.text_input("Banka Hesabı", placeholder="9081823")
        m_anahtar = st.text_input("Banka anahtarı", placeholder="062-0121")
        m_pb = st.text_input("Para birimi (Bn.Tp)", placeholder="USD")
        m_vkn = st.text_input("Vergi No", placeholder="1230037647")
        m_unvan = st.text_input("Hesap sahibi / Unvan", placeholder="AYSA DENİZCİLİK ... A.Ş.")

with sag:
    st.subheader("2️⃣ Tedarikçi belgeleri (PDF)")
    pdf_dosyalar = st.file_uploader(
        "Banka deklarasyonu, tedarikçi bilgi formu, hesap cüzdanı, vergi levhası…",
        type=["pdf"],
        accept_multiple_files=True,
    )

if st.button("🔍 Karşılaştır ve farkları yakala", type="primary", use_container_width=True):
    if not pdf_dosyalar:
        st.error("En az bir PDF belgesi yükleyin.")
        st.stop()
    if not ss_dosyalar and not any([m_iban, m_hesap, m_anahtar, m_vkn, m_unvan]):
        st.error("SDM tarafı için ekran görüntüsü yükleyin ya da manuel veri girin.")
        st.stop()

    # --- SDM tarafını oku ---
    sdm_metin = ""
    for f in ss_dosyalar or []:
        with st.spinner(f"OCR: {f.name}"):
            sdm_metin += "\n" + resim_metni_oku(f.name, f.getvalue())
    sdm = alanlari_cikar(sdm_metin, "SDM ekranı")
    sdm["guncel_ibanlar"], sdm["yeni_ibanlar"] = sdm_bolumle(sdm_metin)

    # manuel girişleri birleştir
    if m_iban:
        i = clean_iban(m_iban)
        if i not in sdm["ibanlar"]:
            sdm["ibanlar"].append(i)
    if m_hesap:
        sdm["hesap_no"] = [re.sub(r"\D", "", m_hesap)] + sdm["hesap_no"]
    if m_anahtar and m_anahtar not in sdm["banka_anahtarlari"]:
        sdm["banka_anahtarlari"].append(m_anahtar.strip())
    if m_pb:
        sdm["para_birimleri"] = list(dict.fromkeys([m_pb.strip().upper()] + sdm["para_birimleri"]))
    if m_vkn:
        sdm["vergi_no"] = list(dict.fromkeys([re.sub(r"\D", "", m_vkn)] + sdm["vergi_no"]))
    if m_unvan:
        sdm["unvanlar"] = [normalize_text(m_unvan)] + sdm["unvanlar"]

    # --- Belgeleri oku ---
    belgeler = []
    for f in pdf_dosyalar:
        with st.spinner(f"Okunuyor: {f.name}"):
            metin = pdf_metni_oku(f.name, f.getvalue())
        belgeler.append(alanlari_cikar(metin, f.name))

    # --- Karşılaştır ---
    bulgular = karsilastir(sdm, belgeler)
    df = pd.DataFrame(bulgular)

    n_fail = (df["Durum"] == FAIL).sum()
    n_warn = (df["Durum"] == WARN).sum()
    n_ok = (df["Durum"] == OK).sum()

    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("✅ Uyumlu", int(n_ok))
    c2.metric("⚠️ Kontrol edilecek", int(n_warn))
    c3.metric("❌ Uyumsuz", int(n_fail))
    talep = sdm.get("talep_no") or "—"
    c4.metric("Talep No", talep)

    if n_fail:
        st.error("❌ UYUMSUZLUK BULUNDU — talebi onaylamadan önce farkları inceleyin!")
    elif n_warn:
        st.warning("⚠️ Bazı alanlar tek kaynaktan teyitli ya da okunamadı — kontrol önerilir.")
    else:
        st.success("✅ Tüm kontroller uyumlu görünüyor.")

    st.subheader("Kontrol sonuçları")
    st.dataframe(df, use_container_width=True, hide_index=True)

    # --- Alan bazında yan yana karşılaştırma ---
    st.subheader("Alan bazında karşılaştırma")
    tum_belge = {
        "ibanlar": [i for b in belgeler for i in b["ibanlar"]],
        "hesap_no": [h for b in belgeler for h in b["hesap_no"]],
        "vergi_no": [v for b in belgeler for v in b["vergi_no"]],
        "para_birimleri": [p for b in belgeler for p in b["para_birimleri"]],
        "unvanlar": [u for b in belgeler for u in b["unvanlar"]],
    }
    satirlar = [
        ("IBAN", ", ".join(iban_bicimle(i) for i in sdm["ibanlar"]) or "—",
         ", ".join(iban_bicimle(i) for i in dict.fromkeys(tum_belge["ibanlar"])) or "—"),
        ("Hesap No", ", ".join(sdm["hesap_no"][:3]) or "—", ", ".join(dict.fromkeys(tum_belge["hesap_no"]))[:120] or "—"),
        ("Banka anahtarı", ", ".join(sdm["banka_anahtarlari"]) or "—", "—"),
        ("Para birimi", ", ".join(sdm["para_birimleri"]) or "—", ", ".join(dict.fromkeys(tum_belge["para_birimleri"])) or "—"),
        ("Vergi No", ", ".join(sdm["vergi_no"][:2]) or "—", ", ".join(dict.fromkeys(tum_belge["vergi_no"])) or "—"),
        ("Unvan", (sdm["unvanlar"] or ["—"])[0], (tum_belge["unvanlar"] or ["—"])[0]),
    ]
    st.dataframe(
        pd.DataFrame(satirlar, columns=["Alan", "SDM ekranı", "Belgeler"]),
        use_container_width=True, hide_index=True,
    )

    # --- Belge detayları ---
    st.subheader("Belge detayları")
    for b in belgeler:
        with st.expander(f"📄 {b['kaynak']} — {len(b['ibanlar'])} IBAN, {len(b['vergi_no'])} VKN adayı"):
            if b["ibanlar"]:
                det = []
                for i in b["ibanlar"]:
                    p = iban_parcala(i)
                    det.append({
                        "IBAN": iban_bicimle(i),
                        "Banka": p.get("banka_adi", "?"),
                        "Mod-97": "Geçerli" if p.get("gecerli") else "GEÇERSİZ",
                    })
                st.dataframe(pd.DataFrame(det), use_container_width=True, hide_index=True)
            st.text_area("OCR / metin çıktısı", b["metin"], height=200, key=f"txt_{b['kaynak']}")

    if sdm_metin.strip():
        with st.expander("🖥️ SDM ekranı OCR çıktısı"):
            st.text_area("SDM metni", sdm_metin, height=200)

    # --- Rapor indir ---
    rapor = io.StringIO()
    rapor.write(f"SDM KONTROL RAPORU — Talep No: {talep}\n" + "=" * 50 + "\n")
    for b_ in bulgular:
        rapor.write(f"{b_['Durum']} [{b_['Kontrol']}] {b_['Detay']}\n")
    st.download_button("📥 Raporu indir (.txt)", rapor.getvalue(), file_name=f"sdm_kontrol_{talep}.txt")
else:
    st.info("Ekran görüntülerini ve PDF'leri yükleyip **Karşılaştır** düğmesine basın.")
