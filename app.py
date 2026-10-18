"""SUT kontrol - Streamlit arayüzü."""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import streamlit as st
# Sayfa sekmesi ve genişlik ayarı (Bu satır tüm st. kodlarından önce olmalı!)
st.set_page_config(page_title="SUTCheck", page_icon="✅", layout="centered")

# Şık ve modern ana başlık
st.markdown("<h1 style='text-align: center; color: #003c71;'>✅ SUTCheck</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>Yapay Zeka Destekli Reçete ve Rapor Analizi</p>", unsafe_allow_html=True)
st.divider()


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

st.markdown("<p style='text-align: center; font-size: 16px; font-weight: bold; color: #a3a8b8;'>DİYABET • STATİN • OSTEOPOROZ • KLOPİDOGREL</p>", unsafe_allow_html=True)


sol, sag = st.columns(2)

with sol:
    st.subheader("📄 Rapor")
    
    # 1. KART: FOTOĞRAF YÜKLEME
    with st.container(border=True):
        rapor_fotolar = st.file_uploader(
            "Rapor fotoğrafları (Birden fazla seçebilirsiniz)",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="rapor_fotolar",
        )
        if rapor_fotolar and st.button("Fotoğrafları oku", key="oku_buton"):
            with st.spinner("Okunuyor..."):
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
                        if ham.get("duzenleme_tarihi"):
                            st.session_state["r_bas_alan"] = tarih_coz(ham.get("duzenleme_tarihi"))
                        if ham.get("bitis_tarihi"):
                            st.session_state["r_bit_alan"] = tarih_coz(ham.get("bitis_tarihi"))
                        if ham.get("hekim_branslari"):
                            st.session_state["r_brans_alan"] = ", ".join(ham.get("hekim_branslari"))

                    
                    
                    if en_guncel_tarih:
                        st.session_state["r_tarih_alan"] = tarih_coz(en_guncel_tarih)
                    if en_guncel_ldl:
                        st.session_state["r_ldl_alan"] = float(en_guncel_ldl)
                        
                    st.session_state["r_hastaliklar_alan"] = list(set(tum_hastaliklar)) 
                    st.session_state["r_tanilar_alan"] = ", ".join(list(set(tum_tanilar)))
                    st.session_state["r_ilaclar_alan"] = "\n".join(list(set(tum_ilaclar)))
                    st.session_state["r_metin_alan"] = tum_metin.strip()
                    st.session_state["rapor_foto_okundu"] = True
                    st.success("Tüm fotoğraflar okundu ve harmanlandı!")
                except Exception as e:
                    st.error(f"Fotoğraf okunamadı: {e}")

    # 2. KART: TEMEL BİLGİLER
    with st.container(border=True):
        c1, c2 = st.columns(2)
        r_bas = c1.date_input("Düzenleme tarihi", key="r_bas_alan", format="DD.MM.YYYY")
        r_bit = c2.date_input("Bitiş tarihi", key="r_bit_alan", format="DD.MM.YYYY")
        r_tani = st.text_input("Tanı kodları (virgülle ayırın)", key="r_tani_alan")
        r_brans = st.text_input("Hekim branşları (virgülle ayırın)", key="r_brans_alan")
        
    # 3. ÇEKMECE: GİZLİ METİN KUTULARI (Göz yormaması için kapalı gelir)
    with st.expander("📝 Rapor İlaçları ve Serbest Metni Düzenle", expanded=False):
        st.caption("Yapay zeka bu alanları fotoğraftan otomatik doldurur. Manuel müdahale için burayı kullanabilirsiniz.")
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

    # --- DİNAMİK ARAYÜZ ---
    aktif_ilaclar = (st.session_state.get("r_ilaclar_alan", "") + " " + st.session_state.get("rec_ilaclar_alan", "")).lower()
    
    r_t_skoru = None
    r_yas = None
    osteo_ilaclar = ["alendronat", "risedronat", "ibandronik", "zoledronik", "denosumab", "fosamax", "actonel", "bonviva", "aclasta", "prolia"]
    
    if any(ilac in aktif_ilaclar for ilac in osteo_ilaclar):
        with st.container(border=True):
            st.info("🦴 Osteoporoz Rapor Bilgileri:")
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                r_yas = st.number_input("👤 Hasta Yaşı:", min_value=1, max_value=120, value=65, step=1, key="r_yas_dinamik")
            with col_o2:
                r_t_skoru = st.number_input("📉 DEXA T-Skoru:", value=None, format="%.2f", key="r_t_skoru_dinamik")

    r_idame = False
    r_6_ay_ara = False
    r_ldl = None
    r_ldl_tarihi = None
    r_ldl_2 = None
    r_ldl_tarihi_2 = None
    r_risk = []
    
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
                    "Diyabet (Diabetes Mellitus)", "Hipertansiyon", "Geçirilmiş MI / Akut Koroner Sendrom", 
                    "Geçirilmiş İnme", "Koroner Arter Hastalığı (KAH)", "Periferik Arter Hastalığı (PAH)",
                    "Abdominal Aort Anevrizması", "Karotis Arter Hastalığı",
                    "Ailede erken kardiyovasküler hastalık öyküsü", "65 yaş ve üzeri"
                ],
                key="r_risk"
            )

with sag:
    st.subheader("🧾 Reçete")
    
    # 1. KART: FOTOĞRAF VE ONAYLAR
    with st.container(border=True):
        recete_foto = st.file_uploader(
            "Reçete fotoğrafı (opsiyonel)",
            type=["jpg", "jpeg", "png"],
            key="recete_foto",
        )
        if recete_foto is not None and st.button("Fotoğraftan oku", key="oku_recete_buton"):
            with st.spinner("Okunuyor..."):
                try:
                    ham_rec = recete_oku_onbellekli(recete_foto.getvalue())
                    st.session_state["rec_no"] = ham_rec.get("recete_no") or ""
                    st.session_state["rec_tarih_alan"] = tarih_coz(ham_rec.get("tarih")) or date.today()
                    st.session_state["rec_brans_alan"] = ham_rec.get("hekim_bransi") or ""
                    st.session_state["rec_ilaclar_alan"] = "\n".join(
                        i.get("ad") for i in (ham_rec.get("ilaclar") or []) if i.get("ad")
                    )
                    st.session_state["rec_aciklama_alan"] = ham_rec.get("aciklama") or ""
                    st.session_state["rec_var"] = True
                    st.session_state["recete_foto_okundu"] = True
                    st.success("Fotoğraf okundu — alanları belgeyle karşılaştırın.")
                except Exception as e:
                    st.error(f"Fotoğraf okunamadı: {e}")
                    
        col_onay1, col_onay2 = st.columns(2)
        with col_onay1:
            rec_var = st.checkbox("Reçete de kontrol edilsin", key="rec_var", value=True)
        with col_onay2:
            rapor_yok = st.checkbox("Bu reçete raporsuz", key="rapor_yok", disabled=not rec_var)

    # 2. KART: TEMEL REÇETE BİLGİLERİ
    with st.container(border=True):
        rec_tarih = st.date_input("Reçete tarihi", key="rec_tarih_alan", format="DD.MM.YYYY", disabled=not rec_var)
        
        # ARB / Osteo Ön Kontrolleri (İlaçları çekmeceden okumadan önce yapay zeka hafızası için)
        rec_ilaclar_gecici = st.session_state.get("rec_ilaclar_alan", "")
        recete_metni = rec_ilaclar_gecici.replace('İ', 'i').replace('I', 'ı').lower() if rec_ilaclar_gecici else ""
        arb_kelimeleri = ["valsartan", "losartan", "kandesartan", "irbesartan", "olmesartan", "telmisartan", "diovan", "atacand", "micardis", "karvea", "co-diovan", "exforge", "tensart", "hyzaar", "ayra"]
        arb_var = any(kelime in recete_metni for kelime in arb_kelimeleri)
        osteo_kelimeleri = ["alendronat", "risedronat", "ibandronat", "zolendronik", "denosumab", "fosamax", "fosomx", "actonel", "bonviva", "zometa", "aclesta", "prolia", "fosavance"]
        osteo_var = any(kelime in recete_metni for kelime in osteo_kelimeleri)

        col_rec1, col_rec2 = st.columns(2)
        with col_rec1:
            rec_brans = st.text_input("Hekim Branşı", key="rec_brans_alan", disabled=not rec_var, placeholder="Aile hekimliği")
        with col_rec2:
            if arb_var:
                rec_kutu = st.number_input("💊 ARB Kutu:", min_value=1, max_value=10, value=1, key="rec_kutu_yeni")
            else:
                rec_kutu = 0

    # 3. ÇEKMECE: REÇETE İLAÇLARI VE AÇIKLAMA
    with st.expander("💊 Reçete İlaçları ve Açıklama (Manuel Düzenle)", expanded=False):
        rec_ilaclar = st.text_area(
            "Reçetedeki ilaçlar — her satıra BİR ÜRÜN",
            height=110,
            key="rec_ilaclar_alan",
            disabled=not rec_var,
        )
        rec_aciklama = st.text_area(
            "Reçete açıklaması",
            height=80,
            key="rec_aciklama_alan",
            disabled=not rec_var,
        )

    # REÇETE OSTEOPOROZ KESİN KONTROL MENÜSÜ
    osteo_yas = 0
    osteo_kirik = "Yok"
    osteo_t_skor = 0.0

    if osteo_var:
        with st.container(border=True):
            st.info("🦴 Reçetede Osteoporoz İlacı Tespit Edildi")
            col_ost1, col_ost2, col_ost3 = st.columns(3)
            with col_ost1:
                osteo_yas = st.number_input("👤 Yaş:", min_value=1, max_value=120, value=65, key="rec_osteo_yas")
            with col_ost2:
                osteo_kirik = st.selectbox("💥 Kırık?", ["Yok", "Var"], key="rec_osteo_kirik")
            with col_ost3:
                osteo_t_skor = st.number_input("📉 T-Skoru:", min_value=-6.0, max_value=2.0, value=-2.5, step=0.1, key="rec_osteo_tskor")


def ekrani_temizle():
    st.session_state.clear()
    for alan in [
        "r_tani_alan", "r_brans_alan", "r_ilaclar_alan", "r_metin_alan",
        "rec_brans_alan", "rec_ilaclar_alan", "rec_aciklama_alan"
    ]:
        st.session_state[alan] = ""
    st.session_state["r_bas_alan"] = date.today()
    st.session_state["r_bit_alan"] = date.today()
    st.session_state["rec_tarih_alan"] = date.today()
    st.session_state["r_t_skoru_dinamik"] = None
    st.session_state["r_yas_dinamik"] = 65
    st.session_state["r_ldl_alan"] = None
    st.session_state["r_ldl_2_alan"] = None
    st.session_state["r_risk"] = []
    st.session_state["r_idame"] = False
    st.session_state["r_6_ay_ara"] = False
    st.session_state["rapor_yok"] = False

onay = True
if st.session_state.get("foto_okundu") or st.session_state.get("recete_foto_okundu"):
    onay = st.checkbox(
        "Fotoğraftan okunan alanları belgeyle karşılaştırdım ve gerekli düzeltmeleri yaptım."
    )

col_btn1, col_btn2 = st.columns([3, 1])
with col_btn1:
    kontrol_basildi = st.button("🔍 Kontrol et", type="primary", use_container_width=True, disabled=not onay)
with col_btn2:
    st.button("🧹 Yeni Hasta / Temizle", use_container_width=True, on_click=ekrani_temizle)

if kontrol_basildi:
    
    if not ks_listesi:
        st.error("Hiçbir kural dosyası yüklenemedi. 'kurallar' klasörünü kontrol edin.")
        st.stop()
     # --- KESİN SUT KURALLARI (Yapay Zekadan Bağımsız) ---
    hekim_bransi = rec_brans.replace('İ', 'i').replace('I', 'ı').lower() if rec_brans else ""
    
    # 1. ARB Kuralı
    if arb_var and rec_kutu > 1 and "aile hekim" in hekim_bransi:
        st.error("🚨 SUT KESİNTİ RİSKİ: Aile Hekimleri raporsuz durumlarda ARB grubu ilaçları en fazla 1 aylık tedavi dozunda yazabilir. Fazlası ödenmez!")
        st.stop()

    # 2. OSTEOPOROZ Kuralı
    if osteo_var:
        if osteo_yas >= 75:
            st.success("✅ 75 yaş ve üzeri hastalarda KMY (T-Skoru) ölçümü şartı aranmaz. Yaş kriterinden ödenir.")
        elif osteo_kirik == "Var" and osteo_t_skor > -1.0:
            st.error(f"🚨 SUT KESİNTİ RİSKİ: Patolojik kırığı olanlarda T-Skoru en az -1.0 olmalıdır (Girilen: {osteo_t_skor}). Ödenmez!")
            st.stop()
        elif osteo_yas >= 65 and osteo_kirik == "Yok" and osteo_t_skor > -2.5:
            st.error(f"🚨 SUT KESİNTİ RİSKİ: 65 yaş ve üzeri (kırık yok) hastalarda T-Skoru en az -2.5 olmalıdır (Girilen: {osteo_t_skor}). Ödenmez!")
            st.stop()
        elif osteo_yas < 65 and osteo_kirik == "Yok" and osteo_t_skor > -3.0:
            st.error(f"🚨 SUT KESİNTİ RİSKİ: 65 yaş altı (kırık yok) hastalarda T-Skoru en az -3.0 olmalıdır (Girilen: {osteo_t_skor}). Ödenmez!")
            st.stop()
    # ----------------------------------------------------
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
        hasta_yasi=r_yas,
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