"""SUT kontrol - Streamlit arayüzü."""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import streamlit as st

from sut import gorsel, ilac, katalog, motor
from sut.semalar import Ilac, Rapor, Recete, Sonuc

KURAL_YOLLARI = [
    Path(__file__).parent / "kurallar" / "antihipertansif.yaml",
    Path(__file__).parent / "kurallar" / "antidiyabetik.yaml",
    Path(__file__).parent / "kurallar" / "statin.yaml",
    Path(__file__).parent / "kurallar" / "kardiyoloji.yaml",
    Path(__file__).parent / "kurallar" / "osteoporoz.yaml", # <-- BUNU EKLE
]

RENK = {"HATA": "#A32D2D", "UYARI": "#854F0B", "BILGI": "#0F6E56"}
ETIKET = {"HATA": "HATA", "UYARI": "UYARI", "BILGI": "BİLGİ"}

st.set_page_config(page_title="SUT Kontrol", page_icon="✓", layout="wide")

@st.cache_resource
def kural_setleri():
    return [(y.stem, motor.yukle(y)) for y in KURAL_YOLLARI if y.exists()]

def ilac_listesi(ham: str) -> list[Ilac]:
    return [Ilac(ad=s.strip()) for s in ham.splitlines() if s.strip()]

def virgullu_liste(ham: str) -> list[str]:
    return [p.strip() for p in ham.replace("\n", ",").split(",") if p.strip()]

def tarih_coz(deger) -> date | None:
    if not deger:
        return None
    try:
        return date.fromisoformat(str(deger)[:10])
    except ValueError:
        return None

def sayi_coz(deger) -> int | None:
    try:
        return int(float(str(deger).strip()))
    except (ValueError, TypeError):
        return None

def float_coz(deger) -> float | None:
    if deger is None:
        return None
    try:
        return float(str(deger).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None

def arb_kutu_toplami(ilaclar: list[dict]) -> tuple[int, bool]:
    toplam, eksik = 0, False
    for i in ilaclar:
        ad = i.get("ad")
        if ad and "ARB" in ilac.siniflari_bul(ad):
            adet = sayi_coz(i.get("adet"))
            if adet is None:
                eksik = True
            else:
                toplam += adet
    return toplam, eksik

@st.cache_data(show_spinner=False)
def rapor_oku_onbellekli(veri: bytes) -> dict:
    return gorsel.rapor_oku(io.BytesIO(veri))

@st.cache_data(show_spinner=False)
def recete_oku_onbellekli(veri: bytes) -> dict:
    return gorsel.recete_oku(io.BytesIO(veri))

# Form alanlarının başlangıç değerleri
for _anahtar, _deger in {
    "r_no": "",
    "r_bas_alan": date.today(),
    "r_bit_alan": date.today(),
    "r_tani_alan": "",
    "r_brans_alan": "",
    "r_ilaclar_alan": "",
    "r_metin_alan": "",
    "foto_okundu": False,
    "rec_var": False,
    "rapor_yok": False,
    "rec_no": "",
    "rec_tarih_alan": date.today(),
    "rec_brans_alan": "",
    "rec_ilaclar_alan": "",
    "rec_kutu": 0,
    "rec_aciklama_alan": "",
    "recete_foto_okundu": False,
    "r_ldl": None,
    "r_ldl_tarih": None,
    "r_ldl_2": None,
    "r_ldl_tarih_2": None,
    "r_risk": [],
    "r_idame": False,
}.items():
    st.session_state.setdefault(_anahtar, _deger)

ks_listesi = kural_setleri()

st.title("SUT kontrol")
if ks_listesi:
    ozet = " · ".join(f"{ad} (sürüm {ks.surum})" for ad, ks in ks_listesi)
else:
    ozet = "HİÇBİR KURAL DOSYASI BULUNAMADI"
st.caption(f"Kural setleri: {ozet} — karar destek aracıdır, nihai sorumluluk kullanıcıdadır.")

sol, sag = st.columns(2)

with sol:
    st.subheader("Rapor")
    
    # --- ÇOKLU FOTOĞRAF YÜKLEME KISMI ---
    rapor_fotolar = st.file_uploader(
        "Rapor fotoğrafları (Birden fazla seçebilirsiniz)",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="rapor_fotolar",
    )
    
    if rapor_fotolar and st.button("Fotoğrafları oku", key="oku_buton"):
        with st.spinner("Gemini tüm raporları inceliyor, lütfen bekleyin..."):
            try:
                tum_metin = ""
                tum_hastaliklar = []
                tum_tanilar = []
                tum_ilaclar = []
                en_guncel_ldl = None
                en_guncel_tarih = None
                
                for foto in rapor_fotolar:
                    ham = rapor_oku_onbellekli(foto.getvalue())
                    
                    if ham.get("serbest_metin"):
                        tum_metin += ham.get("serbest_metin") + "\n\n--- DİĞER RAPOR ---\n\n"
                    if ham.get("hastaliklar"):
                        tum_hastaliklar.extend(ham.get("hastaliklar"))
                    if ham.get("tani_kodlari"):
                        tum_tanilar.extend(ham.get("tani_kodlari"))
                    if ham.get("ilaclar"):
                        tum_ilaclar.extend([i.get("ad") for i in ham.get("ilaclar") if i.get("ad")])
                        
                    if ham.get("ldl_degeri"):
                        en_guncel_ldl = ham.get("ldl_degeri")
                        en_guncel_tarih = ham.get("tarih")
                
                # Verileri ekrana yazdır (Tekrarları set() ile silerek)
                if en_guncel_tarih:
                    st.session_state["r_tarih_alan"] = tarih_coz(en_guncel_tarih)
                if en_guncel_ldl:
                    st.session_state["r_ldl_alan"] = float(en_guncel_ldl)
                    
                st.session_state["r_hastaliklar_alan"] = list(set(tum_hastaliklar)) 
                st.session_state["r_tanilar_alan"] = ", ".join(list(set(tum_tanilar)))
                st.session_state["r_ilaclar_alan"] = "\n".join(list(set(tum_ilaclar)))
                st.session_state["r_metin_alan"] = tum_metin.strip()
                
                st.session_state["rapor_foto_okundu"] = True
                st.success("Tüm fotoğraflar okundu ve başarıyla harmanlandı!")
            except Exception as e:
                st.error(f"Fotoğraf okunamadı: {e}")
    # ------------------------------------

   
    c1, c2 = st.columns(2)
    r_bas = c1.date_input("Düzenleme tarihi", key="r_bas_alan", format="DD.MM.YYYY")
    r_bit = c2.date_input("Bitiş tarihi", key="r_bit_alan", format="DD.MM.YYYY")
    r_tani = st.text_input("Tanı kodları (virgülle ayırın)", key="r_tani_alan")
    r_brans = st.text_input("Hekim branşları (virgülle ayırın)", key="r_brans_alan")
    r_ilaclar = st.text_area(
        "Rapordaki ilaçlar — her satıra BİR ÜRÜN (kutu)",
        height=110,
        key="r_ilaclar_alan",
    )
    r_metin = st.text_area(
        "Raporun serbest metni (tanı, açıklama, not alanlarının tamamı)",
        height=150,
        key="r_metin_alan",
    )
    
# --- DİNAMİK ARAYÜZ (SADECE İLGİLİ İLAÇ YAZILINCA AÇILIR) ---
    
    # Ekrana girilen tüm ilaçları birleştirip kontrol ediyoruz
    aktif_ilaclar = (st.session_state.get("r_ilaclar_alan", "") + " " + st.session_state.get("rec_ilaclar_alan", "")).lower()
    
    # 1. OSTEOPOROZ KONTROLÜ
    r_t_skoru = None
    osteo_ilaclar = ["alendronat", "risedronat", "ibandronik", "zoledronik", "denosumab", "fosamax", "actonel", "bonviva", "aclasta", "prolia"]
    
    if any(ilac in aktif_ilaclar for ilac in osteo_ilaclar):
        st.info("🦴 Osteoporoz ilacı algılandı. Lütfen raporun DEXA skorunu girin:")
        r_t_skoru = st.number_input("DEXA T-Skoru (Örn: -2.6)", value=None, format="%.2f", key="r_t_skoru_dinamik")

    # 2. STATİN (KOLERSTEROL) KONTROLÜ
    r_idame = False
    r_6_ay_ara = False
    r_ldl = None
    r_ldl_tarihi = None
    r_ldl_2 = None
    r_ldl_tarihi_2 = None
    risk_faktorleri = []
    
    
    statin_ilaclar = ["statin", "atorvastatin", "rosuvastatin", "pitavastatin", "pravastatin", "simvastatin", "fluvastatin", "lipitor", "crestor", "zocor", "kolestor"]
    
    if any(ilac in aktif_ilaclar for ilac in statin_ilaclar):
        with st.expander("🩸 Statin / LDL Tahlil Bilgileri", expanded=True):
            r_idame = st.checkbox("İdame (Yenileme) Raporu", key="r_idame")
            r_6_ay_ara = st.checkbox("Tedaviye 6 aydan uzun süre ara verilmiş", key="r_6_ay_ara")
            
            c1, c2 = st.columns(2)
            r_ldl = c1.number_input("Güncel / 1. LDL", value=None, format="%f", key="r_ldl_alan")
            r_ldl_tarihi = c2.date_input("1. LDL Tarihi", value=None, key="r_ldl_tarihi_alan")
            
            c3, c4 = st.columns(2)
            r_ldl_2 = c3.number_input("Eski / 2. LDL (Gerekliyse)", value=None, format="%f", key="r_ldl_2_alan")
            r_ldl_tarihi_2 = c4.date_input("2. LDL Tarihi", value=None, key="r_ldl_tarihi_2_alan")                     
        r_risk = st.multiselect(
            "Ek Risk Faktörleri ve Yüksek Riskli Hastalıklar",
            options=[
                "Diyabet (Diabetes Mellitus)", 
                "Hipertansiyon", 
                "Geçirilmiş MI / Akut Koroner Sendrom", 
                "Geçirilmiş İnme", 
                "Koroner Arter Hastalığı (KAH)", 
                "Periferik Arter Hastalığı (PAH)",
                "Abdominal Aort Anevrizması", 
                "Karotis Arter Hastalığı",
                "Ailede erken kardiyovasküler hastalık öyküsü", 
                "65 yaş ve üzeri"
            ],
            key="r_risk"
        )


with sag:
    st.subheader("Reçete")
    
    # --- GERİ GETİRİLEN REÇETE FOTOĞRAF YÜKLEME KISMI ---
    recete_foto = st.file_uploader(
        "Reçete fotoğrafı (opsiyonel — alanları otomatik doldurur)",
        type=["jpg", "jpeg", "png"],
        key="recete_foto",
    )
    if recete_foto is not None and st.button("Fotoğraftan oku", key="oku_recete_buton"):
        with st.spinner("Gemini reçete fotoğrafını okuyor, birkaç saniye sürebilir..."):
            try:
                ham_rec = recete_oku_onbellekli(recete_foto.getvalue())
                
                st.session_state["rec_no"] = ham_rec.get("recete_no") or ""
                st.session_state["rec_tarih_alan"] = tarih_coz(ham_rec.get("tarih")) or date.today()
                st.session_state["rec_brans_alan"] = ham_rec.get("hekim_bransi") or ""
                
                st.session_state["rec_ilaclar_alan"] = "\n".join(
                    i.get("ad") for i in (ham_rec.get("ilaclar") or []) if i.get("ad")
                )
                st.session_state["rec_aciklama_alan"] = ham_rec.get("aciklama") or ""
                
                st.session_state["rec_var"] = True  # Reçete var kutusunu otomatik işaretle
                st.session_state["recete_foto_okundu"] = True
                st.success("Fotoğraf okundu — aşağıdaki alanları MUTLAKA belgeyle karşılaştırın.")
            except Exception as e:
                st.error(f"Fotoğraf okunamadı: {e}")
    # ----------------------------------------------------
    
    rec_var = st.checkbox("Reçete de kontrol edilsin", key="rec_var")


    rapor_yok = st.checkbox(
        "Bu reçete raporsuz (rapora dayanmıyor)",
        key="rapor_yok",
        disabled=not rec_var,
        help="İşaretlerseniz soldaki rapor bilgileri yok sayılır.",
    )
    
    rec_tarih = st.date_input(
        "Reçete tarihi", key="rec_tarih_alan", format="DD.MM.YYYY", disabled=not rec_var
    )
    rec_brans = st.text_input(
        "Reçeteyi yazan hekimin branşı",
        key="rec_brans_alan",
        disabled=not rec_var,
        placeholder="Aile hekimliği",
    )
    rec_ilaclar = st.text_area(
        "Reçetedeki ilaçlar — her satıra BİR ÜRÜN (kutu)",
        height=110,
        key="rec_ilaclar_alan",
        disabled=not rec_var,
    )
    rec_kutu = st.number_input(
        "ARB içeren ürünlerin toplam kutu sayısı",
        min_value=0,
        step=1,
        key="rec_kutu",
        disabled=not rec_var,
    )
    rec_aciklama = st.text_area(
        "Reçete açıklaması",
        height=100,
        key="rec_aciklama_alan",
        disabled=not rec_var,
    )

onay = True
if st.session_state["foto_okundu"] or st.session_state["recete_foto_okundu"]:
    onay = st.checkbox(
        "Fotoğraftan okunan alanları belgeyle karşılaştırdım ve gerekli düzeltmeleri yaptım."
    )

if st.button("Kontrol et", type="primary", use_container_width=True, disabled=not onay):
    if not ks_listesi:
        st.error("Hiçbir kural dosyası yüklenemedi. 'kurallar' klasörünü kontrol edin.")
        st.stop()

    raporsuz = bool(rec_var and rapor_yok)
    rapor = Rapor(
            no="",  # <-- r_no yerine 
            duzenleme_tarihi=r_bas,
        bitis_tarihi=None if raporsuz else r_bit,
        tani_kodlari=virgullu_liste(r_tani),
        hekim_branslari=virgullu_liste(r_brans),
        ilaclar=[] if raporsuz else ilac_listesi(r_ilaclar),
        serbest_metin="" if raporsuz else r_metin,
        idame_mi=False if (raporsuz or r_6_ay_ara) else r_idame,
        ldl_degeri=None if raporsuz else (float(r_ldl) if r_ldl is not None else None),
        ldl_tarihi=None if raporsuz else r_ldl_tarihi,
        ldl_degeri_2=None if raporsuz else (float(r_ldl_2) if r_ldl_2 is not None else None),
        ldl_tarihi_2=None if raporsuz else r_ldl_tarihi_2,
        risk_faktorleri=[] if raporsuz else r_risk,
        t_skoru=r_t_skoru,
    )
    recete = (
        Recete(
            recete_no="",
            tarih=rec_tarih,
            hekim_bransi=rec_brans or None,
            ilaclar=ilac_listesi(rec_ilaclar),
            rapor_var=not raporsuz,
            aciklama=rec_aciklama,
            arb_kutu_adedi=int(rec_kutu) or None,
        )
        if rec_var
        else None
    )

    if not rapor.ilaclar and not (recete and recete.ilaclar):
        st.warning("En az bir ilaç girin.")
        st.stop()

    tum_bulgular = []
    for _ad, ks in ks_listesi:
        tum_bulgular += motor.calistir(rapor, recete, ks).bulgular
    sirali = {"HATA": 0, "UYARI": 1, "BILGI": 2}
    tum_bulgular.sort(key=lambda b: sirali[b.seviye])
    sonuc = Sonuc(bulgular=tum_bulgular, kural_seti_surumu="birleşik")

    st.divider()
    tum_ilaclar = list(rapor.ilaclar) + (list(recete.ilaclar) if recete else [])
    tanimsiz = [i.ad for i in tum_ilaclar if not i.etken_maddeler]
    if not sonuc.gecerli:
        st.error(f"{len(sonuc.hatalar)} hata, {len(sonuc.uyarilar)} uyarı bulundu.")
    elif tanimsiz:
        st.warning(
            "Engelleyici bulgu yok, ANCAK bazı ilaçlar tanınmadığı için kontrol "
            "eksik yapıldı. Aşağıdaki listeye bakın."
        )
    else:
        st.success(f"Engelleyici bulgu yok. {len(sonuc.uyarilar)} uyarı.")

    bulunan = {}
    for i in tum_ilaclar:
        bulunan.update(i.etken_maddeler)
    if bulunan:
        rozetler = ", ".join(f"{m} ({ilac.sinif_adi(s)})" for m, s in sorted(bulunan.items()))
        st.caption("Tanınan etken maddeler: " + rozetler)
    if tanimsiz:
        st.warning(
            "Şu ilaçların etken maddesi tanınamadı, kurallar bunlar için "
            "çalışmadı: " + ", ".join(tanimsiz)
        )

    for b in sonuc.bulgular:
        renk = RENK[b.seviye]
        with st.container(border=True):
            st.markdown(
                f"<span style='color:{renk};font-weight:500'>{ETIKET[b.seviye]}</span> "
                f"&nbsp;·&nbsp; **{b.baslik}**",
                unsafe_allow_html=True,
            )
            st.write(b.mesaj)
            ayrinti = []
            if b.sut_madde:
                ayrinti.append(f"SUT: {b.sut_madde}")
            if b.kanit:
                ayrinti.append(b.kanit)
            ayrinti.append(f"kural: {b.kural_id}")
            st.caption(" · ".join(ayrinti))