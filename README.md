# 🎈 Blank app template

A simple Streamlit app template for you to modify!

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://blank-app-template.streamlit.app/)

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```

## 🏦 SDM Kontrol Dashboard'u

SDM "Banka Bilgileri Değişikliği" taleplerini tedarikçi belgeleriyle
karşılaştırıp farkları yakalayan dashboard: `sdm_dashboard.py`

```
$ pip install -r requirements.txt
$ streamlit run sdm_dashboard.py
```

**Nasıl çalışır?**

1. SDM ekran görüntülerini (PNG/JPG) yükleyin — Güncel/Yeni Veriler
   bölümleri OCR ile okunur (isterseniz alanları manuel de girebilirsiniz).
2. Tedarikçi PDF'lerini yükleyin (banka bilgisi deklarasyonu, tedarikçi
   bilgi formu, banka hesap cüzdanı, vergi levhası). Metin katmanı olmayan
   taranmış PDF'ler otomatik OCR'lanır (RapidOCR — harici kurulum gerekmez).
3. **Karşılaştır** düğmesi şu kontrolleri çalıştırır:
   - IBAN yapısal doğrulama (mod-97) ve banka kodu ↔ banka adı eşlemesi
   - Yeni eklenen IBAN'ın belgelerde geçip geçmediği (kaç bağımsız kaynakta?)
   - Hesap numarası ↔ IBAN hesap alanı tutarlılığı
   - Banka anahtarı (banka + şube kodu) ↔ IBAN tutarlılığı
   - Para birimi (Bn.Tp) tutarlılığı
   - Vergi numarası eşleşmesi (vergi levhası ↔ formlar)
   - Hesap sahibi / unvan benzerliği
4. Sonuçlar ✅ / ⚠️ / ❌ durumlarıyla listelenir; alan bazında yan yana
   karşılaştırma tablosu ve indirilebilir kontrol raporu üretilir.
