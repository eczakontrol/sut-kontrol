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
    padding-top: 1.8rem !important;
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

.howto-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 22px 24px;
    margin-bottom: 16px;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.03);
}
.howto-badge {
    display: inline-block;
    background: #EFF6FF;
    color: #0055A5;
    border: 1px solid #BFDBFE;
    font-weight: 700;
    font-size: 12px;
    padding: 4px 10px;
    border-radius: 6px;
    margin-bottom: 10px;
}
.howto-title {
    font-size: 18px;
    font-weight: 700;
    color: #0F172A;
    margin-bottom: 8px;
}
.howto-text {
    font-size: 14.5px;
    line-height: 1.65;
    color: #334155;
    margin: 0;
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
    Path(__file__).parent / "kurallar" / "prostat.yaml",
    Path(__file__).parent / "kurallar" / "dmah.yaml",
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
    """Tüm metinleri, tarihleri ve yüklenmiş fotoğrafları tamamen sıfırlar."""
    yeni_sayac = st.session_state.get("uploader_sayac", 0) + 1
    st.session_state.clear()
    st.session_state["uploader_sayac"] = yeni_sayac
    for alan in [
        "r_tani_alan", "r_brans_alan", "r_ilaclar_alan", "r_metin_alan",
        "rec_brans_alan", "rec_tani_alan", "rec_ilaclar_alan", "rec_aciklama_alan"
    ]:
        st.session_state[alan] = ""
    st.session_state["r_bas_alan"] = date.today()
    st.session_state["r_bit_alan"] = date.today()
    st.session_state["rec_tarih_alan"] = date.today()
    st.session_state["r_t_skoru_dinamik"] = 2.5
    st.session_state["r_yas_dinamik"] = 65
    st.session_state["r_ldl_alan"] = None
    st.session_state["r_ldl_tarihi_alan"] = None
    st.session_state["r_ldl_2_alan"] = None
    st.session_state["r_ldl_tarihi_2_alan"] = None
    st.session_state["r_risk"] = []
    st.session_state["r_idame"] = False
    st.session_state["r_6_ay_ara"] = False
    st.session_state["rec_var"] = True
    st.session_state["rapor_yok"] = False

@st.cache_data(show_spinner=False)
def rapor_oku_onbellekli(veri: bytes) -> dict:
    return gorsel.rapor_oku(io.BytesIO(veri))

@st.cache_data(show_spinner=False)
def recete_oku_onbellekli(veri: bytes) -> dict:
    return gorsel.recete_oku(io.BytesIO(veri))

# Başlangıç Değerleri
for _anahtar, _deger in {
    "uploader_sayac": 0,
    "r_no": "",
    "r_bas_alan": date.today(),
    "r_bit_alan": date.today(),
    "r_tani_alan": "",
    "r_brans_alan": "",
    "r_ilaclar_alan": "",
    "r_metin_alan": "",
    "rapor_foto_okundu": False,
    "rec_var": True,
    "rapor_yok": False,
    "rec_no": "",
    "rec_tarih_alan": date.today(),
    "rec_brans_alan": "",
    "rec_tani_alan": "",
    "rec_ilaclar_alan": "",
    "rec_kutu": 0,
    "rec_aciklama_alan": "",
    "recete_foto_okundu": False,
    "r_ldl_alan": None,
    "r_ldl_tarihi_alan": None,
    "r_ldl_2_alan": None,
    "r_ldl_tarihi_2_alan": None,
    "r_t_skoru_dinamik": 2.5,
    "r_yas_dinamik": 65,
    "r_risk": [],
    "r_idame": False,
    "r_6_ay_ara": False,
}.items():
    st.session_state.setdefault(_anahtar, _deger)

ks_listesi = kural_setleri()
up_id = st.session_state["uploader_sayac"]

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

    aktif_sayfa = st.radio(
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

# --- ÜST BAŞLIK ---
st.markdown(f"""
<div class="top-bar">
    <div>Çalışma alanı &nbsp;›&nbsp; <strong>{aktif_sayfa.split(' ', 1)[1]}</strong> &nbsp;·&nbsp; <span style="color:#0055A5; font-weight:600;">Diyabet · Statin · Osteoporoz · Kardiyoloji & NOAK · DMAH · Prostat (BPH)</span></div>
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
    <div style="font-size:13px; color:#475569; margin-bottom:14px;">
        <strong>Her raporu, güvenle inceleyin:</strong> Rapor ve reçete bilgilerini karşılaştırın, SUT kurallarına göre bulguları gerekçeleriyle görün.
    </div>
    """, unsafe_allow_html=True)
with baslik_sag:
    if aktif_sayfa == "📋 Rapor kontrolü":
        st.button("＋ Yeni kontrol", key="ust_yeni_kontrol_btn", use_container_width=True, on_click=ekrani_temizle)


# =====================================================================
# SAYFA 1: NASIL ÇALIŞIR?
# =====================================================================
if aktif_sayfa == "ℹ️ Nasıl çalışır?":
    st.markdown("### ℹ️ SUTCheck Nasıl Çalışır?")
    st.write("SUTCheck, eczane pratiğinde sık karşılaşılan karmaşık SUT kurallarını saniyeler içinde denetlemek ve olası SGK kesintilerini önlemek için tasarlanmış bir karar destek asistanıdır. Sistemi **4 kolay adımda** kullanabilirsiniz:")

    st.markdown("""
    <div class="howto-card">
        <div class="howto-badge">ADIM 1</div>
        <div class="howto-title">📸 Rapor veya Reçete Fotoğrafını Yükleyin (veya Elle Girin)</div>
        <p class="howto-text">
            <strong>Rapor Bilgileri</strong> bölümünden Medula rapor ekranının fotoğrafını (uzun raporlarda birden fazla fotoğraf seçebilirsiniz) yükleyip <strong>"Fotoğrafları oku"</strong> butonuna basın.<br>
            • Yapay zeka; <strong>Düzenleme ve Bitiş Tarihlerini, ICD-10 Tanı Kodlarını, Hekim Branşlarını, İlaçları, Rapor Açıklama Metnini, LDL değerlerini/tarihlerini ve DEXA T-Skorunu</strong> fotoğraftan otomatik olarak okuyup ilgili kutucuklara yerleştirir.<br>
            • Fotoğraf yüklemek istemiyorsanız, bilgileri doğrudan kutucuklara ve <em>"Rapor İlaçları ve Serbest Metni Düzenle"</em> çekmecesine kendiniz de yazabilirsiniz.
        </p>
    </div>

    <div class="howto-card">
        <div class="howto-badge">ADIM 2</div>
        <div class="howto-title">🩺 İlaç Grubuna Özel Dinamik Alanları Kontrol Edin</div>
        <p class="howto-text">
            Sistem, raporda veya reçetede yer alan ilacın grubunu otomatik olarak tanır ve sadece gerekli durumlarda ek kontrol kutularını ekranda açar:<br>
            • <strong>Statinler (Crestor, Lipitor vb.):</strong> İdame rapor durumu, 6 aydan uzun ara verilip verilmediği, 1. ve 2. LDL değerleri/tahlil tarihleri ile ek risk faktörleri paneli açılır.<br>
            • <strong>Osteoporoz (Prolia, Fosamax, Actonel vb.):</strong> Hasta yaşı ve DEXA T-Skoru doğrulama kutusu açılır.<br>
            • <strong>DMAH / Düşük Molekül Ağırlıklı Heparinler (Oksapar, Clexane, Hibor vb.):</strong> Farklı DMAH kombinasyon yasağını, gebelik tanı kodlarında (O22/O30/Z32-Z35) zorunlu <em>gebelik haftası</em> ibaresini, IU/mg doz şeması ve 6 ay / Sağlık Kurulu şartlarını denetler.<br>
            • <strong>Prostat / BPH ve Cardura (Doksazosin):</strong> Tanı kodunda <code>N40</code> varsa BPH kurallarını (Üroloji uzmanı, alfa bloker 1 yıl / 5-ARI 6 ay süre) çalıştırır ve BPH uyarı kodunu hatırlatır; <strong>Cardura (Doksazosin)</strong> için <code>I10-I15</code> (Hipertansiyon) tanı kodu girilmişse Hipertansiyon uyarı kodunu hatırlatır.<br>
            • <strong>Raporsuz Reçeteler:</strong> Sağ taraftan <em>"Bu reçete raporsuz"</em> seçeneğini işaretlediğinizde, sistem reçete tanı kodlarını, reçete hekim branşını ve kutu adedini baz alır.
        </p>
    </div>

    <div class="howto-card">
        <div class="howto-badge">ADIM 3</div>
        <div class="howto-title">🔍 "Kontrol Et" Butonuna Basın ve Bulguları İnceleyin</div>
        <p class="howto-text">
            Bilgileri belgeyle karşılaştırdıktan sonra alttaki mavi <strong>"🔍 Kontrol et"</strong> butonuna tıklayın. Kural motoru tüm SUT kriterlerini tarar ve sonuçları önem sırasına göre renklendirerek listeler:<br>
            • <strong style="color:#d32f2f;">🔴 HATA (Kesinti Riski):</strong> Zorunlu rapor ibaresi eksikliği, tanı kodu uyumsuzluğu, rapor süresi aşımı (örn. Klopidogrel/NOAK > 12 ay, Finasterid/Dutasterid > 6 ay), uygunsuz hekim branşı veya yasaklı ilaç kombinasyonu (örn. ASA intoleransı varken Coraspin/Klogel-A verilmesi).<br>
            • <strong style="color:#f57c00;">🟠 UYARI (Manuel Teyit):</strong> Aile hekimi 24 ay kullanım şartı, DMAH IU/mg doz şeması kontrolü, eksik tarih veya Medula ilaç geçmişinden kontrol edilmesi gereken durumlar.<br>
            • <strong style="color:#003c71;">🔵 BİLGİ (Uygun):</strong> Aranan SUT şartlarının (örn. NOAK 7 maddelik kontrol listesi, LDL/T-skoru eşiği, Medula uyarı kodları) sağlandığını gösteren onay kartları.
        </p>
    </div>

    <div class="howto-card">
        <div class="howto-badge">ADIM 4</div>
        <div class="howto-title">🧹 "Yeni Hasta / Temizle" ile Sıfırlayın</div>
        <p class="howto-text">
            İncelemeniz bittiğinde sağ üstteki <strong>"＋ Yeni kontrol"</strong> veya alttaki <strong>"🧹 Yeni Hasta / Temizle"</strong> butonuna tıklayarak yüklenen tüm fotoğrafları ve form alanlarını tek tuşla temizleyip yeni hastaya geçebilirsiniz.<br>
            <em>Not: Yüklediğiniz hiçbir fotoğraf veya hasta bilgisi kaydedilmez; yalnızca anlık oturumunuzda işlenir.</em>
        </p>
    </div>
    """, unsafe_allow_html=True)


# =====================================================================
# SAYFA 2: KURAL KÜTÜPHANESİ
# =====================================================================
elif aktif_sayfa == "📖 Kural kütüphanesi":
    st.markdown("### 📖 Aktif SUT Kural Kütüphanesi")
    st.write("Sistemde şu anda aktif olarak denetlenen ilaç grupları ve temel SUT kontrol kapsamları aşağıdadır:")

    for kod_adi, ks in ks_listesi:
        with st.expander(f"📘 {ks.kaynak or kod_adi.upper()} (Sürüm: {ks.surum})", expanded=True):
            st.caption(f"Dosya: `kurallar/{kod_adi}.yaml` · Toplam {len(ks.kurallar)} aktif kural denetleniyor.")
            for k in ks.kurallar:
                baslik = k.get("baslik") or k.get("baslik_yok") or k.get("id")
                madde = k.get("sut_madde", "SUT")
                st.markdown(f"- **{baslik}** (`{madde}`)")


# =====================================================================
# SAYFA 3: RAPOR KONTROLÜ (ANA ÇALIŞMA EKRANI)
# =====================================================================
else:
    sol, sag = st.columns(2)

    with sol:
        st.subheader("📄 Rapor Bilgileri")
        
        # 1. KART: FOTOĞRAF YÜKLEME
        with st.container(border=True):
            rapor_fotolar = st.file_uploader(
                "Rapor fotoğrafları (Birden fazla seçebilirsiniz)",
                type=["jpg", "jpeg", "png"],
                accept_multiple_files=True,
                key=f"rapor_fotolar_{up_id}",
            )
            if rapor_fotolar and st.button("Fotoğrafları oku", key="oku_buton", type="primary"):
                with st.spinner("Yapay zeka raporu okuyor ve parametreleri işliyor..."):
                    try:
                        tum_metin = ""
                        tum_tanilar = []
                        tum_ilaclar = []
                        
                        for foto in rapor_fotolar:
                            ham = rapor_oku_onbellekli(foto.getvalue())
                            if ham.get("serbest_metin"):
                                tum_metin += ham.get("serbest_metin") + "\n\n--- DİĞER RAPOR ---\n\n"
                            if ham.get("tani_kodlari"):
                                tum_tanilar.extend(ham.get("tani_kodlari"))
                            if ham.get("ilaclar"):
                                tum_ilaclar.extend([i.get("ad") for i in ham.get("ilaclar") if i.get("ad")])
                            
                            # Otomatik 1. ve 2. LDL + Tarih Çekme
                            if ham.get("ldl_degeri") is not None:
                                st.session_state["r_ldl_alan"] = float_coz(ham.get("ldl_degeri"))
                            if ham.get("ldl_tarihi") or ham.get("tarih"):
                                t1 = tarih_coz(ham.get("ldl_tarihi") or ham.get("tarih"))
                                if t1:
                                    st.session_state["r_ldl_tarihi_alan"] = t1

                            if ham.get("ldl_2_degeri") is not None:
                                st.session_state["r_ldl_2_alan"] = float_coz(ham.get("ldl_2_degeri"))
                            if ham.get("ldl_2_tarihi"):
                                t2 = tarih_coz(ham.get("ldl_2_tarihi"))
                                if t2:
                                    st.session_state["r_ldl_tarihi_2_alan"] = t2

                            # Otomatik T-Skoru ve Yaş Çekme
                            if ham.get("t_skoru") is not None:
                                t_val = float_coz(ham.get("t_skoru"))
                                if t_val is not None:
                                    st.session_state["r_t_skoru_dinamik"] = abs(t_val)
                                    st.session_state["rec_osteo_tskor"] = -abs(t_val)
                            if ham.get("hasta_yasi") is not None:
                                try:
                                    yas_val = int(ham.get("hasta_yasi"))
                                    st.session_state["r_yas_dinamik"] = yas_val
                                    st.session_state["rec_osteo_yas"] = yas_val
                                except (ValueError, TypeError):
                                    pass

                            if ham.get("idame_tedavisi") is not None:
                                st.session_state["r_idame"] = bool(ham.get("idame_tedavisi"))
                            if ham.get("alti_ay_ara") is not None:
                                st.session_state["r_6_ay_ara"] = bool(ham.get("alti_ay_ara"))
                            if ham.get("risk_faktorleri"):
                                st.session_state["r_risk"] = ham.get("risk_faktorleri")
                            if ham.get("duzenleme_tarihi"):
                                dt = tarih_coz(ham.get("duzenleme_tarihi"))
                                if dt:
                                    st.session_state["r_bas_alan"] = dt
                            if ham.get("bitis_tarihi"):
                                bt = tarih_coz(ham.get("bitis_tarihi"))
                                if bt:
                                    st.session_state["r_bit_alan"] = bt
                            if ham.get("hekim_branslari"):
                                st.session_state["r_brans_alan"] = ", ".join(ham.get("hekim_branslari"))

                        if tum_tanilar:
                            st.session_state["r_tani_alan"] = ", ".join(list(dict.fromkeys(tum_tanilar)))
                        st.session_state["r_ilaclar_alan"] = "\n".join(list(dict.fromkeys(tum_ilaclar)))
                        st.session_state["r_metin_alan"] = tum_metin.strip()
                        st.session_state["rapor_foto_okundu"] = True
                        st.success("Tüm fotoğraflar okundu; tanı, LDL, T-Skoru ve tarihler otomatik işlendi!")
                    except Exception as e:
                        st.error(f"Fotoğraf okunamadı: {e}")

        # 2. KART: TEMEL RAPOR BİLGİLERİ
        with st.container(border=True):
            c1, c2 = st.columns(2)
            r_bas = c1.date_input("Düzenleme tarihi", key="r_bas_alan", format="DD.MM.YYYY")
            r_bit = c2.date_input("Bitiş tarihi", key="r_bit_alan", format="DD.MM.YYYY")
            r_tani = st.text_input("Rapor Tanı Kodları (ICD-10, virgülle ayırın)", key="r_tani_alan", placeholder="Örn. N40, I48, O22.0, Z34.9")
            r_brans = st.text_input("Rapor Hekim Branşları (virgülle ayırın)", key="r_brans_alan", placeholder="Örn. Üroloji, Kardiyoloji, Kadın Hastalıkları ve Doğum")
            
        # 3. ÇEKMECE: RAPOR İLAÇLARI VE SERBEST METİN
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

        # --- DİNAMİK ARAYÜZLER (YALNIZCA OSTEOPOROZ VE STATİN İÇİN) ---
        aktif_ilaclar = (st.session_state.get("r_ilaclar_alan", "") + " " + st.session_state.get("rec_ilaclar_alan", "")).lower()

        # 1. OSTEOPOROZ DİNAMİK PANELİ
        r_t_skoru = None
        r_yas = 65
        osteo_ilaclar = ["alendronat", "risedronat", "ibandronik", "zoledronik", "denosumab", "fosamax", "actonel", "bonviva", "aclasta", "prolia", "fosavance"]

        if any(ad in aktif_ilaclar for ad in osteo_ilaclar):
            with st.container(border=True):
                st.info("🦴 Osteoporoz Rapor Bilgileri (Otomatik / Manuel):")
                col_o1, col_o2 = st.columns(2)
                with col_o1:
                    r_yas = st.number_input(
                        "👤 Hasta Yaşı:", min_value=1, max_value=120,
                        step=1, key="r_yas_dinamik",
                    )
                with col_o2:
                    r_t_skoru_ham = st.number_input(
                        "📉 DEXA T-Skoru (-):", min_value=0.0,
                        max_value=6.0, step=0.1, format="%.1f",
                        key="r_t_skoru_dinamik",
                    )
                    r_t_skoru = -abs(r_t_skoru_ham) if r_t_skoru_ham is not None else None

        # 2. STATİN / LDL DİNAMİK PANELİ
        r_idame = False
        r_6_ay_ara = False
        r_ldl = None
        r_ldl_tarihi = None
        r_ldl_2 = None
        r_ldl_tarihi_2 = None
        r_risk = []
        statin_ilaclar = ["statin", "atorvastatin", "rosuvastatin", "pitavastatin", "pravastatin", "simvastatin", "fluvastatin", "lipitor", "crestor", "zocor", "kolestor", "ator", "rovu", "tarden", "alvastin"]

        if any(ilac_adi in aktif_ilaclar for ilac_adi in statin_ilaclar):
            with st.expander("🩸 Statin / LDL Tahlil Bilgileri", expanded=True):
                r_idame = st.checkbox("İdame (Yenileme) Raporu", key="r_idame")
                r_6_ay_ara = st.checkbox("Tedaviye 6 aydan uzun süre ara verilmiş", key="r_6_ay_ara")
                
                c1, c2 = st.columns(2)
                r_ldl = c1.number_input("Güncel / 1. LDL", value=None, format="%f", key="r_ldl_alan")
                r_ldl_tarihi = c2.date_input("1. LDL Tarihi", value=None, key="r_ldl_tarihi_alan", format="DD.MM.YYYY")

                c3, c4 = st.columns(2)
                r_ldl_2 = c3.number_input("Eski / 2. LDL (Gerekliyse)", value=None, format="%f", key="r_ldl_2_alan")
                r_ldl_tarihi_2 = c4.date_input("2. LDL Tarihi", value=None, key="r_ldl_tarihi_2_alan", format="DD.MM.YYYY")
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
                key=f"recete_foto_{up_id}",
            )
            if recete_foto is not None and st.button("Fotoğraftan oku", key="oku_recete_buton", type="primary"):
                with st.spinner("Reçete fotoğrafı okunuyor..."):
                    try:
                        ham_rec = recete_oku_onbellekli(recete_foto.getvalue())
                        st.session_state["rec_no"] = ham_rec.get("recete_no") or ""
                        st.session_state["rec_tarih_alan"] = tarih_coz(ham_rec.get("tarih")) or date.today()
                        st.session_state["rec_brans_alan"] = ham_rec.get("hekim_bransi") or ""
                        if ham_rec.get("tani_kodlari"):
                            st.session_state["rec_tani_alan"] = ", ".join(list(dict.fromkeys(ham_rec.get("tani_kodlari"))))
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
                rec_var = st.checkbox("Reçete de kontrol edilsin", key="rec_var")
            with col_onay2:
                rapor_yok = st.checkbox("Bu reçete raporsuz", key="rapor_yok", disabled=not rec_var)

        # 2. KART: TEMEL REÇETE BİLGİLERİ
        with st.container(border=True):
            rec_ilaclar_gecici = st.session_state.get("rec_ilaclar_alan", "")
            recete_metni = rec_ilaclar_gecici.replace('İ', 'i').replace('I', 'ı').lower() if rec_ilaclar_gecici else ""
            arb_kelimeleri = ["valsartan", "losartan", "kandesartan", "irbesartan", "olmesartan", "telmisartan", "diovan", "atacand", "micardis", "karvea", "co-diovan", "exforge", "tensart", "hyzaar", "ayra", "klopidogrel", "plavix", "karum", "pingel"]
            kutu_sor = any(kelime in recete_metni for kelime in arb_kelimeleri)
            osteo_var = any(kelime in recete_metni for kelime in osteo_ilaclar)

            r_c1, r_c2 = st.columns(2)
            with r_c1:
                rec_tarih = st.date_input("Reçete tarihi", key="rec_tarih_alan", format="DD.MM.YYYY", disabled=not rec_var)
            with r_c2:
                rec_brans = st.text_input("Reçeteyi Yazan Hekim Branşı", key="rec_brans_alan", disabled=not rec_var, placeholder="Örn. Üroloji, Aile hekimliği")

            rec_tani = st.text_input(
                "Reçete Tanı Kodları (ICD-10, virgülle ayırın)",
                key="rec_tani_alan",
                disabled=not rec_var,
                placeholder="Örn. N40, I10, O22.0 (Raporsuz kontrolde bu tanılar esas alınır)"
            )

            if kutu_sor:
                rec_kutu = st.number_input("💊 Reçetedeki Kutu Adedi:", min_value=1, max_value=10, value=1, key="rec_kutu_yeni")
            else:
                rec_kutu = 0

        # 3. ÇEKMECE: REÇETE İLAÇLARI VE AÇIKLAMA
        with st.expander("💊 Reçete İlaçları ve Açıklama (Manuel Düzenle)", expanded=False):
            st.caption("Reçetedeki ilaçları ve açıklama bilgisini buradan görebilir veya düzenleyebilirsiniz.")
            rec_ilaclar = st.text_area(
                "Reçetedeki ilaçlar — her satıra BİR ÜRÜN",
                height=110,
                key="rec_ilaclar_alan",
                disabled=not rec_var,
            )
            rec_aciklama = st.text_area(
                "Reçete açıklaması",
                height=150,
                key="rec_aciklama_alan",
                disabled=not rec_var,
            )

        # REÇETE OSTEOPOROZ HIZLI KONTROL PANELİ
        osteo_yas = 65
        osteo_kirik = "Yok"
        osteo_t_skor = -2.5

        if osteo_var and rapor_yok:
            with st.container(border=True):
                st.info("🦴 Reçetede Osteoporoz İlacı Tespit Edildi")
                col_ost1, col_ost2, col_ost3 = st.columns(3)
                with col_ost1:
                    osteo_yas = st.number_input("👤 Yaş:", min_value=1, max_value=120, step=1, key="rec_osteo_yas")
                with col_ost2:
                    osteo_kirik = st.selectbox("💥 Kırık?", ["Yok", "Var"], key="rec_osteo_kirik")
                with col_ost3:
                    osteo_t_skor = st.number_input("📉 T-Skoru:", min_value=-6.0, max_value=2.0, step=0.1, key="rec_osteo_tskor")

    onay = True
    if st.session_state.get("rapor_foto_okundu") or st.session_state.get("recete_foto_okundu"):
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

        rapor_tani_list = virgullu_liste(r_tani)
        recete_tani_list = virgullu_liste(rec_tani) if rec_var else []
        birlesik_tanilar = list(dict.fromkeys(rapor_tani_list + recete_tani_list))

        rapor = Rapor(
            rapor_no=st.session_state.get("r_no") or None,
            duzenleme_tarihi=None if raporsuz else r_bas,
            bitis_tarihi=None if raporsuz else r_bit,
            tani_kodlari=recete_tani_list if raporsuz else birlesik_tanilar,
            hekim_branslari=virgullu_liste(r_brans),
            ilaclar=[] if raporsuz else ilac_listesi(r_ilaclar),
            serbest_metin="" if raporsuz else r_metin,
            idame_mi=False if (raporsuz or r_6_ay_ara) else r_idame,
            ldl_degeri=None if raporsuz else r_ldl,
            ldl_tarihi=None if raporsuz else r_ldl_tarihi,
            ldl_degeri_2=None if raporsuz else r_ldl_2,
            ldl_tarihi_2=None if raporsuz else r_ldl_tarihi_2,
            risk_faktorleri=[] if raporsuz else r_risk,
            t_skoru=osteo_t_skor if (raporsuz and osteo_var) else r_t_skoru,
            hasta_yasi=osteo_yas if (raporsuz and osteo_var) else r_yas,
        )

        recete = (
            Recete(
                recete_no=st.session_state.get("rec_no") or None,
                tarih=rec_tarih,
                hekim_bransi=rec_brans or None,
                tani_kodlari=recete_tani_list,
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

            kanit_html = (
                f'<div style="margin-top:6px; font-size:12px; color:#475569;"><strong>Kanıt / Detay:</strong> {b.kanit}</div>'
                if b.kanit else ""
            )
            sut_html = (
                f'<span style="float:right; font-size:11.5px; font-weight:600; color:#475569; background:rgba(255,255,255,0.6); padding:2px 8px; border-radius:4px;">{b.sut_madde}</span>'
                if b.sut_madde else ""
            )

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
                    {sut_html}
                    <span style="color: {renk}; font-weight: 700; font-size: 15px;">
                        {b.seviye} &nbsp;·&nbsp; {b.baslik}
                    </span>
                    <p style="color: #1e2329; margin-top: 8px; margin-bottom: 0; font-size: 14px;">
                        {b.mesaj}
                    </p>
                    {kanit_html}
                </div>
                """,
                unsafe_allow_html=True
            )