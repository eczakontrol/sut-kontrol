"""SUT kontrol - Streamlit arayüzü."""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import streamlit as st
from sut import gorsel, ilac, katalog, motor
from sut.semalar import Ilac, Rapor, Recete, Sonuc

# Sayfa yapılandırması
st.set_page_config(
    page_title="SUTCheck · Eczacı Karar Destek Aracı",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- KURUMSAL MAVİ-BEYAZ SAAS TASARIMI (CSS) ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap');

.stApp {
    background-color: #F8FAFC;
    font-family: 'Inter', sans-serif;
}

.block-container {
    padding-top: 2rem !important;
    padding-bottom: 2rem !important;
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0A1E3C 0%, #0F294A 100%) !important;
    border-right: 1px solid #1E3A8A;
}
section[data-testid="stSidebar"] * {
    color: #F8FAFC !important;
}

.sidebar-brand {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 8px 4px 20px 4px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.12);
    margin-bottom: 18px;
}
.brand-plus {
    width: 40px;
    height: 40px;
    border: 1.5px solid rgba(255, 255, 255, 0.35);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    font-weight: 500;
    background: rgba(255, 255, 255, 0.06);
}
.brand-title {
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 26px;
    font-weight: 700;
    line-height: 1.1;
    letter-spacing: -0.5px;
}
.brand-sub {
    font-size: 12px;
    opacity: 0.75;
    margin-top: 3px;
}

.privacy-box {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 10px;
    padding: 16px;
    margin-top: 28px;
}
.privacy-title {
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 18px;
    font-weight: 600;
    margin: 6px 0;
}
.privacy-desc {
    font-size: 12px;
    line-height: 1.5;
    opacity: 0.8;
}

.top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 10px;
    margin-bottom: 14px;
    border-bottom: 1px solid #E2E8F0;
    font-size: 12.5px;
    color: #475569;
}
.secure-pill {
    background: #EFF6FF;
    color: #1D4ED8;
    border: 1px solid #BFDBFE;
    padding: 4px 10px;
    border-radius: 20px;
    font-weight: 600;
    font-size: 11.5px;
}

div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div,
div[data-baseweb="select"] > div {
    background-color: #FFFFFF !important;
    border: 1px solid #CBD5E1 !important;
    border-radius: 8px !important;
    color: #0F172A !important;
}
div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea {
    color: #0F172A !important;
    background-color: #FFFFFF !important;
}
section[data-testid="stFileUploaderDropzone"] {
    background-color: #F8FAFC !important;
    border: 1.5px dashed #93C5FD !important;
    border-radius: 10px !important;
    color: #1E293B !important;
}
section[data-testid="stFileUploaderDropzone"] * {
    color: #334155 !important;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.03);
}
div.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0055A5 0%, #1D4ED8 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 0.65rem 1.4rem !important;
}
</style>
""", unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---
KURAL_YOLLARI = [
    Path(__file__).parent / "kurallar" / "antihipertansif.yaml",
    Path(__file__).parent / "kurallar" / "antidiyabetik.yaml",
    Path(__file__).parent / "kurallar" / "statin.yaml",
    Path(__file__).parent / "kurallar" / "kardiyoloji.yaml",
    Path(__file__).parent / "kurallar" / "osteoporoz.yaml",
]

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

def float_coz(deger) -> float | None:
    if deger is None:
        return None
    try:
        return float(str(deger).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None

def ekrani_temizle():
    st.session_state.clear()
    st.session_state.pop("rapor_fotolar", None)
    st.session_state.pop("recete_foto", None)
    st.rerun()

@st.cache_data(show_spinner=False)
def rapor_oku_onbellekli(veri: bytes) -> dict:
    return gorsel.rapor_oku(io.BytesIO(veri))

@st.cache_data(show_spinner=False)
def recete_oku_onbellekli(veri: bytes) -> dict:
    return gorsel.recete_oku(io.BytesIO(veri))

# Başlangıç Değerleri
for _anahtar, _deger in {
    "r_no": "",
    "r_bas_alan": date.today(),
    "r_bit_alan": date.today(),
    "r_tani_alan": "",
    "r_brans_alan": "",
    "r_ilaclar_alan": "",
    "r_metin_alan": "",
    "rec_var": False,
    "rapor_yok": False,
    "rec_no": "",
    "rec_tarih_alan": date.today(),
    "rec_brans_alan": "",
    "rec_tani_alan": "",
    "rec_ilaclar_alan": "",
    "rec_kutu": 0,
    "rec_aciklama_alan": "",
    "r_ldl_alan": None,
    "r_ldl_tarihi_alan": None,
    "r_ldl_2_alan": None,
    "r_ldl_tarihi_2_alan": None,
    "r_risk": [],
    "r_idame": False,
    "r_6_ay_ara": False,
}.items():
    st.session_state.setdefault(_anahtar, _deger)

ks_listesi = kural_setleri()

# --- SOL MENÜ (SIDEBAR) ---
with st.sidebar:
    st.markdown("""
    <div class="sidebar-brand">
        <div class="brand-plus">+</div>
        <div>
            <div class="brand-title">SUTCheck</div>
            <div class="brand-sub">Eczacı karar destek aracı</div>
        </div>
    </div>
    <div style="font-size:11px; letter-spacing:1.2px; opacity:0.65; margin-bottom:10px; font-weight:600;">
        ÇALIŞMA ALANI
    </div>
    """, unsafe_allow_html=True)

    st.radio(
        "Menü",
        ["📋 Rapor kontrolü", "📖 Kural kütüphanesi", "ℹ️ Nasıl çalışır?"],
        label_visibility="collapsed"
    )

    st.markdown("""
    <div class="privacy-box">
        <div style="font-size:18px;">🛡️</div>
        <div class="privacy-title">Verileriniz size ait.</div>
        <div class="privacy-desc">
            Belge bilgileri yalnızca bu oturumda, anlık olarak işlenir. Sunucuda kalıcı olarak depolanmaz.
        </div>
        <div style="margin-top:12px; font-size:11.5px; font-weight:600; color:#60A5FA !important;">
            ● Güvenli ve geçici çalışma
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- ÜST BÖLÜM VE ADIM ÇUBUĞU ---
st.markdown("""
<div class="top-bar">
    <div>Çalışma alanı &nbsp;›&nbsp; <strong>Rapor kontrolü</strong> &nbsp;·&nbsp; <span style="color:#0055A5; font-weight:600;">Diyabet · Statin · Osteoporoz · Kardiyoloji & NOAK</span></div>
    <div class="secure-pill">🔒 Güvenli yerel oturum</div>
</div>
""", unsafe_allow_html=True)

baslik_sol, baslik_sag = st.columns([5, 1])
with baslik_sol:
    st.markdown("""
    <div style="display:flex; align-items:baseline; gap:12px; margin-bottom:2px;">
        <span style="font-family:'Playfair Display', Georgia, serif; font-size:32px; font-weight:700; color:#0055A5; letter-spacing:-0.5px;">
            🛡️ SUTCheck
        </span>
        <span style="font-size:13px; font-weight:600; color:#64748B;">
            • &nbsp;Yapay Zeka Destekli Eczacı Karar Destek Sistemi
        </span>
    </div>
    <div style="font-size:13px; color:#475569; margin-bottom:10px;">
        <strong>Her raporu, güvenle inceleyin:</strong> Rapor ve reçete bilgilerini karşılaştırın, SUT kurallarına göre bulguları gerekçeleriyle görün.
    </div>
    """, unsafe_allow_html=True)
with baslik_sag:
    st.button("＋ Yeni kontrol", key="ust_yeni_kontrol_btn", use_container_width=True, on_click=ekrani_temizle)

st.markdown("""
<div style="display:flex; align-items:center; justify-content:space-between; background:#FFFFFF; border:1px solid #E2E8F0; border-radius:8px; padding:8px 16px; margin-bottom:16px; font-size:12px;">
    <div style="display:flex; align-items:center; gap:8px;">
        <span style="background:#EFF6FF; border:1px solid #0055A5; color:#0055A5; font-weight:700; border-radius:4px; padding:2px 7px;">1</span>
        <span><strong>Raporu okutun/girin</strong> <span style="color:#64748B;">(OCR veya manuel)</span></span>
    </div>
    <div style="flex:1; height:1px; background:#E2E8F0; margin:0 12px;"></div>
    <div style="display:flex; align-items:center; gap:8px;">
        <span style="background:#EFF6FF; border:1px solid #0055A5; color:#0055A5; font-weight:700; border-radius:4px; padding:2px 7px;">2</span>
        <span><strong>Belgeyle doğrulayın</strong> <span style="color:#64748B;">(Tanı, branş, değerler)</span></span>
    </div>
    <div style="flex:1; height:1px; background:#E2E8F0; margin:0 12px;"></div>
    <div style="display:flex; align-items:center; gap:8px;">
        <span style="background:#EFF6FF; border:1px solid #0055A5; color:#0055A5; font-weight:700; border-radius:4px; padding:2px 7px;">3</span>
        <span><strong>Sonuçları inceleyin</strong> <span style="color:#64748B;">(Gerekçeli SUT bulguları)</span></span>
    </div>
</div>
""", unsafe_allow_html=True)

# --- ÇALIŞMA SÜTUNLARI ---
sol, sag = st.columns(2)

with sol:
    st.subheader("📄 Rapor Bilgileri")
    
    # 1. KART: FOTOĞRAF YÜKLEME
    with st.container(border=True):
        rapor_fotolar = st.file_uploader(
            "Rapor fotoğrafları (Birden fazla seçebilirsiniz)",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="rapor_fotolar",
        )
        if rapor_fotolar and st.button("Fotoğrafları oku", key="oku_buton", type="primary"):
            with st.spinner("Yapay zeka raporu okuyor ve parametreleri işliyor..."):
                try:
                    tum_metin = ""
                    tum_hastaliklar = []
                    tum_tanilar = []
                    tum_ilaclar = []
                    
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
                        
                        # Otomatik LDL ve Tarih Çekme
                        if ham.get("ldl_degeri"):
                            st.session_state["r_ldl_alan"] = float_coz(ham.get("ldl_degeri"))
                        if ham.get("tarih") or ham.get("ldl_tarihi"):
                            tarih_val = tarih_coz(ham.get("tarih") or ham.get("ldl_tarihi"))
                            if tarih_val:
                                st.session_state["r_ldl_tarihi_alan"] = tarih_val

                        if ham.get("ldl_2_degeri"):
                            st.session_state["r_ldl_2_alan"] = float_coz(ham.get("ldl_2_degeri"))
                        if ham.get("ldl_2_tarihi"):
                            tarih_val_2 = tarih_coz(ham.get("ldl_2_tarihi"))
                            if tarih_val_2:
                                st.session_state["r_ldl_tarihi_2_alan"] = tarih_val_2

                        if ham.get("idame_tedavisi") is not None:
                            st.session_state["r_idame"] = ham.get("idame_tedavisi")
                        if ham.get("alti_ay_ara") is not None:
                            st.session_state["r_6_ay_ara"] = ham.get("alti_ay_ara")
                        if ham.get("risk_faktorleri"):
                            st.session_state["r_risk"] = ham.get("risk_faktorleri")
                        if ham.get("duzenleme_tarihi"):
                            st.session_state["r_bas_alan"] = tarih_coz(ham.get("duzenleme_tarihi"))
                        if ham.get("bitis_tarihi"):
                            st.session_state["r_bit_alan"] = tarih_coz(ham.get("bitis_tarihi"))
                        if ham.get("hekim_branslari"):
                            st.session_state["r_brans_alan"] = ", ".join(ham.get("hekim_branslari"))
                        if ham.get("tani_kodlari"):
                            st.session_state["r_tani_alan"] = ", ".join(list(set(ham.get("tani_kodlari"))))

                    st.session_state["r_ilaclar_alan"] = "\n".join(list(set(tum_ilaclar)))
                    st.session_state["r_metin_alan"] = tum_metin.strip()
                    st.session_state["rapor_foto_okundu"] = True
                    st.success("Tüm fotoğraflar başarıyla okundu, LDL değerleri ve tarihler işlendi!")
                except Exception as e:
                    st.error(f"Fotoğraf okunamadı: {e}")

    # 2. KART: TEMEL BİLGİLER
    with st.container(border=True):
        c1, c2 = st.columns(2)
        r_bas = c1.date_input("Düzenleme tarihi", key="r_bas_alan", format="DD.MM.YYYY")
        r_bit = c2.date_input("Bitiş tarihi", key="r_bit_alan", format="DD.MM.YYYY")
        r_tani = st.text_input("Tanı kodları (ICD-10, virgülle ayırın)", key="r_tani_alan", placeholder="Örn. I48, I10, E11.9")
        r_brans = st.text_input("Hekim branşları (virgülle ayırın)", key="r_brans_alan", placeholder="Örn. Kardiyoloji, İç Hastalıkları")
        
    # 3. ÇEKMECE: GİZLİ METİN KUTULARI
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
    r_yas = 65
    r_idame = False
    r_6_ay_ara = False
    r_ldl = None
    r_ldl_tarihi = None
    r_ldl_2 = None
    r_ldl_tarihi_2 = None
    r_risk = []
    osteo_ilaclar = ["alendronat", "risedronat", "ibandronik", "zoledronik", "denosumab", "fosamax", "actonel", "bonviva", "aclasta", "prolia"]

    if any(ad in aktif_ilaclar for ad in osteo_ilaclar):
        col_sol, _col_sag = st.columns([1.1, 0.9])
        with col_sol:
            with st.container(border=True):
                st.info("🦴 Osteoporoz Rapor Bilgileri:")
                col_o1, col_o2 = st.columns(2)
                with col_o1:
                    r_yas = st.number_input(
                        "👤 Hasta Yaşı:", min_value=1, max_value=120,
                        value=65, step=1, key="r_yas_dinamik",
                    )
                with col_o2:
                    r_t_skoru_ham = st.number_input(
                        "T-Skoru (-)", value=2.5, min_value=0.0,
                        max_value=6.0, step=0.1, format="%.1f",
                        key="r_t_skoru_dinamik",
                    )
                    r_t_skoru = -abs(r_t_skoru_ham) if r_t_skoru_ham is not None else None

    statin_ilaclar = ["statin", "atorvastatin", "rosuvastatin", "pitavastatin", "pravastatin", "simvastatin", "fluvastatin", "lipitor", "crestor", "zocor", "kolestor"]

    if any(ilac_adi in aktif_ilaclar for ilac_adi in statin_ilaclar):
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
    st.subheader("🧾 Reçete Bilgileri")
    
    # 1. KART: FOTOĞRAF VE ONAYLAR
    with st.container(border=True):
        recete_foto = st.file_uploader(
            "Reçete fotoğrafı (opsiyonel)",
            type=["jpg", "jpeg", "png"],
            key="recete_foto",
        )
        if recete_foto is not None and st.button("Fotoğraftan oku", key="oku_recete_buton", type="primary"):
            with st.spinner("Okunuyor..."):
                try:
                    ham_rec = recete_oku_onbellekli(recete_foto.getvalue())
                    st.session_state["rec_no"] = ham_rec.get("recete_no") or ""
                    st.session_state["rec_tarih_alan"] = tarih_coz(ham_rec.get("tarih")) or date.today()
                    st.session_state["rec_brans_alan"] = ham_rec.get("hekim_bransi") or ""
                    if ham_rec.get("tani_kodlari"):
                        st.session_state["rec_tani_alan"] = ", ".join(ham_rec.get("tani_kodlari"))
                    st.session_state["rec_ilaclar_alan"] = "\n".join(
                        i.get("ad") for i in (ham_rec.get("ilaclar") or []) if i.get("ad")
                    )
                    st.session_state["rec_aciklama_alan"] = ham_rec.get("aciklama") or ""
                    st.session_state["rec_var"] = True
                    st.session_state["recete_foto_okundu"] = True
                    st.success("Reçete fotoğrafı başarıyla okundu!")
                except Exception as e:
                    st.error(f"Fotoğraf okunamadı: {e}")
                    
        col_onay1, col_onay2 = st.columns(2)
        with col_onay1:
            rec_var = st.checkbox("Reçete de kontrol edilsin", key="rec_var", value=True)
        with col_onay2:
            rapor_yok = st.checkbox("Bu reçete raporsuz", key="rapor_yok", disabled=not rec_var)

    # 2. KART: TEMEL REÇETE BİLGİLERİ (TANİ KODU EKLENDİ)
    with st.container(border=True):
        rec_tarih = st.date_input("Reçete tarihi", key="rec_tarih_alan", format="DD.MM.YYYY", disabled=not rec_var)
        
        rec_ilaclar_gecici = st.session_state.get("rec_ilaclar_alan", "")
        recete_metni = rec_ilaclar_gecici.replace('İ', 'i').replace('I', 'ı').lower() if rec_ilaclar_gecici else ""
        arb_kelimeleri = ["valsartan", "losartan", "kandesartan", "irbesartan", "olmesartan", "telmisartan", "diovan", "atacand", "micardis", "karvea", "co-diovan", "exforge", "tensart", "hyzaar", "ayra"]
        arb_var = any(kelime in recete_metni for kelime in arb_kelimeleri)
        osteo_kelimeleri = ["alendronat", "risedronat", "ibandronat", "zolendronik", "denosumab", "fosamax", "fosomx", "actonel", "bonviva", "zometa", "aclesta", "prolia", "fosavance"]
        osteo_var = any(kelime in recete_metni for kelime in osteo_kelimeleri)

        col_rec1, col_rec2 = st.columns(2)
        with col_rec1:
            rec_brans = st.text_input("Hekim Branşı", key="rec_brans_alan", disabled=not rec_var, placeholder="Örn. Aile hekimliği")
        with col_rec2:
            rec_tani = st.text_input("Reçete Tanı Kodları", key="rec_tani_alan", disabled=not rec_var, placeholder="Örn. I48")

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

onay = True
if st.session_state.get("foto_okundu") or st.session_state.get("recete_foto_okundu"):
    onay = st.checkbox(
        "Fotoğraftan okunan alanları belgeyle karşılaştırdım ve gerekli düzeltmeleri yaptım."
    )

col_btn1, col_btn2 = st.columns([3, 1])
with col_btn1:
    kontrol_basildi = st.button("🔍 Kontrol et", key="alt_kontrol_btn", type="primary", use_container_width=True, disabled=not onay)
with col_btn2:
    st.button("🧹 Yeni Hasta / Temizle", key="alt_temizle_btn", use_container_width=True, on_click=ekrani_temizle)

if kontrol_basildi:
    if not ks_listesi:
        st.error("Hiçbir kural dosyası yüklenemedi. 'kurallar' klasörünü kontrol edin.")
        st.stop()

    raporsuz = bool(rec_var and rapor_yok)

    # Tanı kodlarını birleştirme (Rapor + Reçete tanıları)
    tum_tanilar = virgullu_liste(r_tani)
    if rec_var and st.session_state.get("rec_tani_alan"):
        tum_tanilar.extend(virgullu_liste(st.session_state.get("rec_tani_alan")))

    # --- KESİN SUT KURALLARI ---
    hekim_bransi = rec_brans.replace('İ', 'i').replace('I', 'ı').lower() if rec_brans else ""

    if raporsuz and arb_var and rec_kutu > 1 and "aile hekim" in hekim_bransi:
        st.error("🚨 SUT KESİNTİ RİSKİ: Aile Hekimleri raporsuz durumlarda ARB grubu ilaçları en fazla 1 aylık tedavi dozunda yazabilir. Fazlası ödenmez!")
        st.stop()

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

    rapor = Rapor(
        rapor_no=st.session_state.get("r_no") or None,
        duzenleme_tarihi=r_bas,
        bitis_tarihi=None if raporsuz else r_bit,
        tani_kodlari=list(set(tum_tanilar)),
        hekim_branslari=virgullu_liste(r_brans),
        ilaclar=[] if raporsuz else ilac_listesi(r_ilaclar),
        serbest_metin="" if raporsuz else r_metin,
        idame_mi=False if (raporsuz or r_6_ay_ara) else r_idame,
        ldl_degeri=None if raporsuz else r_ldl,
        ldl_tarihi=None if raporsuz else r_ldl_tarihi,
        ldl_degeri_2=None if raporsuz else r_ldl_2,
        ldl_tarihi_2=None if raporsuz else r_ldl_tarihi_2,
        risk_faktorleri=[] if raporsuz else r_risk,
        t_skoru=r_t_skoru,
        hasta_yasi=r_yas,
    )

    recete = (
        Recete(
            recete_no=st.session_state.get("rec_no") or None,
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
        if b.seviye == "HATA":
            renk = "#d32f2f"
            bg_renk = "#fde8e8"
        elif b.seviye == "UYARI":
            renk = "#f57c00"
            bg_renk = "#fff4e5"
        else:
            renk = "#003c71"
            bg_renk = "#eef4f9"

        st.markdown(
            f"""
            <div style="
                padding: 15px; 
                border-radius: 8px; 
                background-color: {bg_renk}; 
                border-left: 5px solid {renk}; 
                margin-bottom: 10px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            ">
                <span style="color: {renk}; font-weight: 700; font-size: 15px;">
                    {b.seviye} &nbsp;·&nbsp; {b.baslik}
                </span>
                <p style="color: #1e2329; margin-top: 8px; margin-bottom: 0; font-size: 14px;">
                    {b.mesaj}
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )