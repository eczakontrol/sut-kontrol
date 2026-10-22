"""SUT kontrol - Streamlit arayüzü.

Çalıştırmak için:  streamlit run app.py

Akış: rapor ve/veya reçete fotoğrafı yükle -> Gemini oku -> kullanıcı gözden
geçirip düzeltir -> onay kutusu -> kural motoru çalışır.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import streamlit as st

from sut import gorsel, ilac, katalog, motor
from sut.semalar import Ilac, Rapor, Recete

KURAL_YOLU = Path(__file__).parent / "kurallar" / "antihipertansif.yaml"

RENK = {"HATA": "#A32D2D", "UYARI": "#854F0B", "BILGI": "#0F6E56"}
ETIKET = {"HATA": "HATA", "UYARI": "UYARI", "BILGI": "BİLGİ"}

st.set_page_config(page_title="SUT Kontrol", page_icon="✓", layout="wide")


@st.cache_resource
def kural_seti():
    return motor.yukle(KURAL_YOLU)


@st.cache_data(show_spinner=False)
def rapor_oku_onbellekli(veri: bytes) -> dict:
    """Aynı görüntü tekrar okunursa Gemini'ye yeniden gitmez (kota tasarrufu)."""
    return gorsel.rapor_oku(io.BytesIO(veri))


@st.cache_data(show_spinner=False)
def recete_oku_onbellekli(veri: bytes) -> dict:
    return gorsel.recete_oku(io.BytesIO(veri))


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


def arb_kutu_toplami(ilaclar: list[dict]) -> tuple[int, bool]:
    """ARB içeren ürünlerin toplam kutu sayısı. İkinci değer: kutu sayısı okunamayan var mı."""
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
}.items():
    st.session_state.setdefault(_anahtar, _deger)

ks = kural_seti()

st.title("SUT kontrol")
st.caption(
    f"Kural seti: antihipertansif · sürüm {ks.surum} — "
    "karar destek aracıdır, nihai sorumluluk kullanıcıdadır."
)

sol, sag = st.columns(2)

with sol:
    st.subheader("Rapor")

    rapor_foto = st.file_uploader(
        "Rapor fotoğrafı (opsiyonel — alanları otomatik doldurur)",
        type=["jpg", "jpeg", "png"],
        key="rapor_foto",
    )
    if rapor_foto is not None and st.button("Fotoğraftan oku", key="oku_buton"):
        with st.spinner("Gemini rapor fotoğrafını okuyor, birkaç saniye sürebilir..."):
            try:
                ham = rapor_oku_onbellekli(rapor_foto.getvalue())

                bas = tarih_coz(ham.get("duzenleme_tarihi"))
                bit = tarih_coz(ham.get("bitis_tarihi"))

                st.session_state["r_no"] = ham.get("rapor_no") or ""
                st.session_state["r_bas_alan"] = bas or date.today()
                st.session_state["r_bit_alan"] = bit or date.today()
                st.session_state["r_tani_alan"] = ", ".join(ham.get("tani_kodlari") or [])
                st.session_state["r_brans_alan"] = ", ".join(ham.get("hekim_branslari") or [])
                st.session_state["r_ilaclar_alan"] = "\n".join(
                    i.get("ad") for i in (ham.get("ilaclar") or []) if i.get("ad")
                )
                st.session_state["r_metin_alan"] = ham.get("serbest_metin") or ""
                st.session_state["foto_okundu"] = True
                st.session_state["ham_json"] = ham

                st.success("Fotoğraf okundu — aşağıdaki alanları MUTLAKA belgeyle karşılaştırın.")
                if bas is None or bit is None:
                    st.warning("Tarihlerden biri okunamadı, elle girin.")
            except Exception as e:
                st.error(f"Fotoğraf okunamadı: {e}")

    if "ham_json" in st.session_state:
        with st.expander("Gemini'nin okuduğu ham veri (rapor)"):
            st.json(st.session_state["ham_json"])

    r_no = st.text_input("Rapor no", key="r_no")
    c1, c2 = st.columns(2)
    r_bas = c1.date_input("Düzenleme tarihi", key="r_bas_alan", format="DD.MM.YYYY")
    r_bit = c2.date_input("Bitiş tarihi", key="r_bit_alan", format="DD.MM.YYYY")
    r_tani = st.text_input("Tanı kodları (virgülle ayırın)", key="r_tani_alan")
    r_brans = st.text_input("Hekim branşları (virgülle ayırın)", key="r_brans_alan")
    r_ilaclar = st.text_area(
        "Rapordaki ilaçlar — her satıra BİR ÜRÜN (kutu)",
        height=110,
        key="r_ilaclar_alan",
        placeholder="Valsartan/Amlodipin 160/5 mg",
        help=(
            "Kombinasyon tableti tek satır yazılır: 'Valsartan/Amlodipin 160/5 mg'. "
            "Ayrı kutular ayrı satır yazılır. Monoterapi ibaresi yalnızca aynı "
            "üründe ARB+KKB varsa aranır, bu yüzden satır ayrımı önemlidir."
        ),
    )
    r_metin = st.text_area(
        "Raporun serbest metni (tanı, açıklama, not alanlarının tamamı)",
        height=150,
        key="r_metin_alan",
        placeholder="Esansiyel hipertansiyon. Monoterapi ile kan basıncı...",
    )


with sag:
    st.subheader("Reçete")

    recete_foto = st.file_uploader(
        "Reçete fotoğrafı (opsiyonel — alanları otomatik doldurur)",
        type=["jpg", "jpeg", "png"],
        key="recete_foto",
    )
    if recete_foto is not None and st.button("Reçeteyi fotoğraftan oku", key="recete_oku_buton"):
        with st.spinner("Gemini reçete fotoğrafını okuyor, birkaç saniye sürebilir..."):
            try:
                ham_r = recete_oku_onbellekli(recete_foto.getvalue())
                ilaclar_r = [i for i in (ham_r.get("ilaclar") or []) if i.get("ad")]
                kutu, kutu_eksik = arb_kutu_toplami(ilaclar_r)

                st.session_state["rec_var"] = True
                st.session_state["rec_no"] = ham_r.get("recete_no") or ""
                st.session_state["rec_tarih_alan"] = tarih_coz(ham_r.get("tarih")) or date.today()
                st.session_state["rec_brans_alan"] = ham_r.get("hekim_bransi") or ""
                st.session_state["rec_ilaclar_alan"] = "\n".join(i["ad"] for i in ilaclar_r)
                st.session_state["rec_kutu"] = 0 if kutu_eksik else kutu
                st.session_state["rec_aciklama_alan"] = ham_r.get("aciklama") or ""
                st.session_state["recete_foto_okundu"] = True
                st.session_state["recete_ham_json"] = ham_r
                st.session_state["recete_rapor_notu"] = ham_r.get("rapor_bilgisi")
                st.session_state["recete_kutu_eksik"] = kutu_eksik

                st.success("Reçete okundu — aşağıdaki alanları MUTLAKA belgeyle karşılaştırın.")
                if tarih_coz(ham_r.get("tarih")) is None:
                    st.warning("Reçete tarihi okunamadı, elle girin.")
            except Exception as e:
                st.error(f"Reçete okunamadı: {e}")

    if st.session_state["recete_foto_okundu"]:
        if st.session_state.get("recete_kutu_eksik"):
            st.warning(
                "ARB içeren bir ilacın kutu sayısı okunamadı. Kutu sayısını elle girin."
            )
        rapor_notu = st.session_state.get("recete_rapor_notu")
        if rapor_notu:
            st.info(f"Reçetede rapor bilgisi okundu: {rapor_notu}")
        else:
            st.warning(
                "Reçetede rapor bilgisi bulunamadı. Bu reçete raporsuzsa aşağıdaki "
                "'raporsuz' kutusunu siz işaretleyin. (Otomatik işaretlemiyorum.)"
            )
    if "recete_ham_json" in st.session_state:
        with st.expander("Gemini'nin okuduğu ham veri (reçete)"):
            st.json(st.session_state["recete_ham_json"])

    rec_var = st.checkbox("Reçete de kontrol edilsin", key="rec_var")
    rapor_yok = st.checkbox(
        "Bu reçete raporsuz (rapora dayanmıyor)",
        key="rapor_yok",
        disabled=not rec_var,
        help="İşaretlerseniz soldaki rapor bilgileri yok sayılır.",
    )
    rec_no = st.text_input("Reçete no", key="rec_no", disabled=not rec_var)
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
        placeholder="Valsartan/Amlodipin 160/5 mg",
    )
    rec_kutu = st.number_input(
        "ARB içeren ürünlerin toplam kutu sayısı",
        min_value=0,
        step=1,
        key="rec_kutu",
        disabled=not rec_var,
        help="0 = girilmedi. Raporsuz reçetede ayda en fazla 1 kutu kontrol edilir.",
    )
    rec_aciklama = st.text_area(
        "Reçete açıklaması",
        height=100,
        key="rec_aciklama_alan",
        disabled=not rec_var,
        placeholder="Raporsuz ARB+KKB reçetesinde monoterapi ibaresi burada aranır",
    )


onay = True
if st.session_state["foto_okundu"] or st.session_state["recete_foto_okundu"]:
    onay = st.checkbox(
        "Fotoğraftan okunan alanları belgeyle karşılaştırdım ve gerekli düzeltmeleri yaptım."
    )

if st.button("Kontrol et", type="primary", use_container_width=True, disabled=not onay):
    raporsuz = bool(rec_var and rapor_yok)
    rapor = Rapor(
        rapor_no=None if raporsuz else (r_no or None),
        duzenleme_tarihi=None if raporsuz else r_bas,
        bitis_tarihi=None if raporsuz else r_bit,
        tani_kodlari=virgullu_liste(r_tani),
        hekim_branslari=virgullu_liste(r_brans),
        ilaclar=[] if raporsuz else ilac_listesi(r_ilaclar),
        serbest_metin="" if raporsuz else r_metin,
    )
    recete = (
        Recete(
            recete_no=rec_no or None,
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

    sonuc = motor.calistir(rapor, recete, ks)

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

    # Barkod doğrulaması (SGK EK-4/A kataloğu)
    if katalog.yuklu_mu():
        for i in tum_ilaclar:
            for barkod in katalog.barkodlari_bul(i.ad):
                kayit = katalog.bul(barkod)
                if kayit:
                    st.caption(
                        f"Barkod {barkod}: SGK listesinde — {kayit['a']} "
                        f"(kamu kodu {kayit['k']})"
                    )
                else:
                    st.warning(
                        f"Barkod {barkod} SGK EK-4/A listesinde bulunamadı. "
                        "Barkodu ve ilacı kontrol edin."
                    )
            for kkod in katalog.kamu_kodlarini_bul(i.ad):
                kayit = katalog.kamu_kodu_ile_bul(kkod)
                if kayit:
                    st.caption(f"Kamu kodu {kkod}: SGK listesinde — {kayit['a']}")
                else:
                    st.warning(
                        f"Kamu kodu {kkod} SGK EK-4/A listesinde bulunamadı. "
                        "Kodu ve ilacı kontrol edin."
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
            if b.guven is not None:
                ayrinti.append(f"ibare benzerliği: {b.guven:.2f}")
            ayrinti.append(f"kural: {b.kural_id}")
            st.caption(" · ".join(ayrinti))
