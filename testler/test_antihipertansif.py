"""Antihipertansif kural testleri.

Bu testler projenin güvenlik ağı. Yeni kural eklediğinizde veya
metin normalizasyonuna dokunduğunuzda `pytest` çalıştırın; bir şeyi
bozup bozmadığınızı 2 saniyede öğrenirsiniz.

Kritik ayrım: monoterapi ibaresi yalnızca ARB ile KKB'yi AYNI üründe
birleştiren kombinasyonlarda aranır. Ayrı kutularda yazıldığında aranmaz.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sut import ilac, motor  # noqa: E402
from sut.semalar import Ilac, Rapor, Recete  # noqa: E402

KURAL_YOLU = Path(__file__).resolve().parents[1] / "kurallar" / "antihipertansif.yaml"

IBARE = "Monoterapi ile kan basıncı kontrol altına alınamamıştır."


@pytest.fixture(scope="module")
def ks():
    return motor.yukle(KURAL_YOLU)


def _rapor(ilac_adlari: list[str], metin: str = "") -> Rapor:
    """Her liste elemanı BİR ÜRÜN (kutu) demektir.

    Kombinasyon tableti tek eleman olarak yazılır:
        ["Valsartan/Amlodipin 160/5 mg"]
    Ayrı kutular iki eleman olarak yazılır:
        ["Valsartan 160 mg", "Amlodipin 5 mg"]
    """
    return Rapor(
        duzenleme_tarihi=date(2026, 1, 1),
        bitis_tarihi=date(2027, 12, 31),
        ilaclar=[Ilac(ad=a) for a in ilac_adlari],
        serbest_metin=metin,
    )


def _raporsuz_recete(
    ilac_adlari: list[str],
    kutu: int | None = 1,
    aciklama: str = "",
    brans: str | None = None,
) -> Recete:
    return Recete(
        tarih=date(2026, 6, 1),
        hekim_bransi=brans,
        ilaclar=[Ilac(ad=a) for a in ilac_adlari],
        rapor_var=False,
        aciklama=aciklama,
        arb_kutu_adedi=kutu,
    )


def _kodlar(sonuc, seviye: str | None = None) -> set[str]:
    return {b.kural_id for b in sonuc.bulgular if seviye is None or b.seviye == seviye}


# --- Ana kural: aynı üründe ARB + KKB ---------------------------------------

def test_kombinasyon_urunu_ibare_yoksa_hata(ks):
    r = _rapor(["Valsartan/Amlodipin 160/5 mg"], "Esansiyel hipertansiyon.")
    assert "ARB_KKB_MONOTERAPI" in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_kombinasyon_urunu_ibare_varsa_hata_yok(ks):
    r = _rapor(["Valsartan/Amlodipin 160/5 mg"], f"Esansiyel hipertansiyon. {IBARE}")
    assert "ARB_KKB_MONOTERAPI" not in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_uclu_kombinasyon_ibare_ister(ks):
    """ARB + KKB + diüretik: içinde ARB+KKB olduğu için ibare aranır."""
    r = _rapor(["Valsartan/Amlodipin/Hidroklorotiyazid"], "Esansiyel hipertansiyon.")
    assert "ARB_KKB_MONOTERAPI" in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_iki_kombinasyon_urunu_tek_bulgu_uretir(ks):
    r = _rapor(["Valsartan/Amlodipin", "Olmesartan/Amlodipin"], "Hipertansiyon.")
    sonuc = motor.calistir(r, None, ks)
    assert len([b for b in sonuc.bulgular if b.kural_id == "ARB_KKB_MONOTERAPI"]) == 1


# --- Ayrı kutularda yazıldığında kural tetiklenmez --------------------------

def test_ayri_kutularda_ibare_aranmaz(ks):
    r = _rapor(["Telmisartan 80 mg", "Lerkanidipin 10 mg"], "Hipertansiyon.")
    assert "ARB_KKB_MONOTERAPI" not in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_ayri_kutularda_bilgi_notu_verilir(ks):
    """Sessizce atlamaz: kullanıcıya neden kontrol edilmediğini söyler."""
    r = _rapor(["Telmisartan 80 mg", "Lerkanidipin 10 mg"], "Hipertansiyon.")
    assert "ARB_KKB_AYRI_URUN" in _kodlar(motor.calistir(r, None, ks), "BILGI")


def test_kombinasyon_varken_ayrik_not_verilmez(ks):
    r = _rapor(["Valsartan/Amlodipin"], "Hipertansiyon.")
    assert "ARB_KKB_AYRI_URUN" not in _kodlar(motor.calistir(r, None, ks))


# --- İbare varyasyonları ----------------------------------------------------

def test_buyuk_harfli_ibare_taninir(ks):
    """Türkçe büyük harf tuzağı: 'I' -> 'ı', 'İ' -> 'i'."""
    metin = "MONOTERAPİ İLE KAN BASINCI KONTROL ALTINA ALINAMAMIŞTIR"
    r = _rapor(["Olmesartan/Amlodipin"], metin)
    assert "ARB_KKB_MONOTERAPI" not in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_aksansiz_ibare_taninir(ks):
    metin = "monoterapi ile kan basinci kontrol altina alinamamistir"
    r = _rapor(["Irbesartan/Amlodipin"], metin)
    assert "ARB_KKB_MONOTERAPI" not in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_ocr_gurultusune_dayanikli(ks):
    metin = "Monoterapi ile kan basinci kontrol altlna alinamamistlr"
    r = _rapor(["Valsartan/Amlodipin"], metin)
    assert "ARB_KKB_MONOTERAPI" not in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_alakasiz_metin_ibare_sayilmaz(ks):
    metin = "Hastanın kan basıncı ölçümleri kontrol edilmiştir."
    r = _rapor(["Valsartan/Amlodipin"], metin)
    assert "ARB_KKB_MONOTERAPI" in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_gercek_rapor_cumlesi_taninir(ks):
    """Gerçek raporda hekimin yazdığı biçim (SGK yazısındaki ifade)."""
    metin = (
        "Hastanın monoterapi ile kan basıncının yeterli oranda kontrol altına "
        "alınmadığı için kombine tedaviye geçilmiştir."
    )
    r = _rapor(["Valsartan/Amlodipin 160/5 mg"], metin)
    assert "ARB_KKB_MONOTERAPI" not in _kodlar(motor.calistir(r, None, ks), "HATA")


# --- Ters anlam tuzağı: "alınmıştır" ibarenin tam tersidir -------------------

@pytest.mark.parametrize(
    "metin",
    [
        "Monoterapi ile kan basıncı kontrol altına alınmıştır.",
        "MONOTERAPİ İLE KAN BASINCI KONTROL ALTINA ALINMIŞTIR.",
    ],
)
def test_ters_anlamli_cumle_ibare_sayilmaz(ks, metin):
    r = _rapor(["Valsartan/Amlodipin 160/5 mg"], metin)
    assert "ARB_KKB_MONOTERAPI" in _kodlar(motor.calistir(r, None, ks), "HATA")


@pytest.mark.parametrize(
    "metin",
    [
        "Monoterapi ile kan basıncı kontrol altına alınamamıştır.",
        "Monoterapi ile kan basıncı kontrol altına alınamadı.",
        "MONOTERAPİ İLE KAN BASINCI KONTROL ALTINA ALINAMAMIŞTIR.",
    ],
)
def test_dogru_olumsuz_cumle_kabul_edilir(ks, metin):
    r = _rapor(["Valsartan/Amlodipin 160/5 mg"], metin)
    assert "ARB_KKB_MONOTERAPI" not in _kodlar(motor.calistir(r, None, ks), "HATA")


# --- İbare gerekmeyen kombinasyonlar ----------------------------------------

def test_arb_diuretik_ibare_gerekmez(ks):
    r = _rapor(["Valsartan/Hidroklorotiyazid 160/12,5"], "Esansiyel hipertansiyon.")
    sonuc = motor.calistir(r, None, ks)
    assert not sonuc.hatalar
    assert "ARB_DIURETIK_IBARE_GEREKMEZ" in _kodlar(sonuc, "BILGI")


def test_arb_tek_basina_ibare_gerekmez(ks):
    assert not motor.calistir(_rapor(["Valsartan 160 mg"], "HT."), None, ks).hatalar


def test_ace_tek_basina_ibare_gerekmez(ks):
    assert not motor.calistir(_rapor(["Ramipril 5 mg"], "HT."), None, ks).hatalar


def test_ace_kkb_kombinasyonu_ibare_gerekmez(ks):
    r = _rapor(["Perindopril/Amlodipin 5/5 mg"], "HT.")
    assert not motor.calistir(r, None, ks).hatalar


def test_ace_diuretik_kombinasyonu_ibare_gerekmez(ks):
    r = _rapor(["Ramipril/Hidroklorotiyazid 5/25 mg"], "HT.")
    assert not motor.calistir(r, None, ks).hatalar


def test_gercek_rapor_hata_vermez(ks):
    """Fotoğraftan okunan gerçek rapor: ACE + KKB + indapamid içeren tek kutu."""
    r = _rapor(
        [
            "DOKSAZOSIN MEZILAT",
            "FENOFIBRAT",
            "NEBIVOLOL HCL",
            "PERINDOPRIL+INDAPAMIT+AMLODIPIN",
        ],
        "Hastanın monoterapi ile kan basıncının yeterli oranda kontrol altına "
        "alınmadığı için kombine tedaviye geçilmiştir.",
    )
    assert not motor.calistir(r, None, ks).hatalar


# --- Yardımcı kurallar ------------------------------------------------------

def test_ace_arb_birlikte_uyari_verir(ks):
    """Kapsam 'tumu': ayrı kutularda olsa da yakalanır."""
    r = _rapor(["Ramipril 5 mg", "Valsartan 160 mg"], "HT.")
    assert "RAS_CIFTLI_BLOKAJ" in _kodlar(motor.calistir(r, None, ks), "UYARI")


def test_recetedeki_ilac_raporda_yoksa_hata(ks):
    r = _rapor(["Valsartan 160 mg"], "HT.")
    rec = Recete(tarih=date(2026, 6, 1), ilaclar=[Ilac(ad="Bisoprolol 5 mg")])
    assert "RECETE_RAPOR_KAPSAM" in _kodlar(motor.calistir(r, rec, ks), "HATA")


def test_rapor_suresi_dolmussa_hata(ks):
    r = _rapor(["Valsartan 160 mg"], "HT.")
    rec = Recete(tarih=date(2028, 3, 1), ilaclar=[Ilac(ad="Valsartan 160 mg")])
    assert "RAPOR_SURE" in _kodlar(motor.calistir(r, rec, ks), "HATA")


# --- Raporsuz reçete --------------------------------------------------------

@pytest.mark.parametrize("brans", ["Aile hekimliği", "Kardiyoloji", None])
def test_raporsuz_arb_bir_kutu_brans_fark_etmez(ks, brans):
    rec = _raporsuz_recete(["Valsartan 160 mg"], kutu=1, brans=brans)
    assert not motor.calistir(Rapor(), rec, ks).hatalar


def test_raporsuz_arb_iki_kutu_hata(ks):
    rec = _raporsuz_recete(["Valsartan 160 mg"], kutu=2, brans="Kardiyoloji")
    assert "RAPORSUZ_ARB_RECETE_KUTU" in _kodlar(motor.calistir(Rapor(), rec, ks), "HATA")


def test_raporsuz_kutu_girilmediyse_uyari(ks):
    rec = _raporsuz_recete(["Valsartan 160 mg"], kutu=None)
    assert "RAPORSUZ_ARB_RECETE_KUTU" in _kodlar(motor.calistir(Rapor(), rec, ks), "UYARI")


def test_raporsuz_arb_diuretik_ibare_gerekmez(ks):
    rec = _raporsuz_recete(["Valsartan/Hidroklorotiyazid 160/12,5"], kutu=1)
    assert not motor.calistir(Rapor(), rec, ks).hatalar


def test_raporsuz_arb_kkb_ibare_yoksa_hata(ks):
    rec = _raporsuz_recete(["Valsartan/Amlodipin 160/5 mg"], kutu=1, aciklama="")
    assert "RAPORSUZ_ARB_RECETE_IBARE" in _kodlar(motor.calistir(Rapor(), rec, ks), "HATA")


def test_raporsuz_uclu_kombinasyon_ibare_yoksa_hata(ks):
    rec = _raporsuz_recete(["Valsartan/Amlodipin/Hidroklorotiyazid"], kutu=1)
    assert "RAPORSUZ_ARB_RECETE_IBARE" in _kodlar(motor.calistir(Rapor(), rec, ks), "HATA")


def test_raporsuz_arb_kkb_ibare_varsa_hata_yok(ks):
    rec = _raporsuz_recete(["Valsartan/Amlodipin 160/5 mg"], kutu=1, aciklama=IBARE)
    assert not motor.calistir(Rapor(), rec, ks).hatalar


def test_raporsuz_ters_anlamli_aciklama_hata(ks):
    rec = _raporsuz_recete(
        ["Valsartan/Amlodipin 160/5 mg"],
        kutu=1,
        aciklama="Monoterapi ile kan basıncı kontrol altına alınmıştır.",
    )
    assert "RAPORSUZ_ARB_RECETE_IBARE" in _kodlar(motor.calistir(Rapor(), rec, ks), "HATA")


def test_raporsuz_arb_disi_ilac_bu_kurali_tetiklemez(ks):
    rec = _raporsuz_recete(["Ramipril 5 mg"], kutu=5)
    assert not any(k.startswith("RAPORSUZ_ARB") for k in _kodlar(motor.calistir(Rapor(), rec, ks)))


def test_raporlu_recetede_kutu_siniri_yok(ks):
    """Raporlu reçetede 3 aylık doz yazılabilir; kutu sınırı uygulanmaz."""
    r = _rapor(["Valsartan 160 mg"], "HT.")
    rec = Recete(
        tarih=date(2026, 6, 1),
        ilaclar=[Ilac(ad="Valsartan 160 mg")],
        rapor_var=True,
        arb_kutu_adedi=3,
    )
    assert not any(k.startswith("RAPORSUZ_ARB") for k in _kodlar(motor.calistir(r, rec, ks)))


# --- Etken madde ve marka tanıma --------------------------------------------

@pytest.mark.parametrize(
    "ad, beklenen",
    [
        ("Ramipril 5 mg", {"ACE"}),
        ("CANDESARTAN 16 MG", {"ARB"}),
        ("Amlodipin 10 mg", {"KKB"}),
        ("Valsartan/HCTZ 160/12,5", {"ARB", "DIURETIK"}),
        ("PERINDOPRIL+INDAPAMIT+AMLODIPIN", {"ACE", "DIURETIK", "KKB"}),
        ("Exforge 5/160 mg", {"ARB", "KKB"}),
        ("Exforge HCT 10/160/12,5", {"ARB", "KKB", "DIURETIK"}),
        ("Triplixam", {"ACE", "DIURETIK", "KKB"}),
        ("Cozaar 50 mg", {"ARB"}),
        ("Bilinmeyen Ilac 10 mg", set()),
    ],
)
def test_sinif_tanima(ad, beklenen):
    assert ilac.siniflari_bul(ad) == beklenen


def test_marka_adiyla_yazilan_kombinasyon_ibare_ister(ks):
    r = _rapor(["Exforge"], "Esansiyel hipertansiyon.")
    assert "ARB_KKB_MONOTERAPI" in _kodlar(motor.calistir(r, None, ks), "HATA")

    # --- Rapor dışı, raporsuz da yazılabilen ARB kullanımı -----------------------

def test_arb_tek_basina_rapor_disinda_da_gecer(ks):
    """Rapor başka bir ilaç için (ör. ACE), reçetede ayrıca ARB tek başına
    yazılmış: SUT'a göre bu raporsuz da yazılabildiği için kapsam hatası vermemeli."""
    r = _rapor(["Ramipril 5 mg"], "HT.")
    rec = Recete(tarih=date(2026, 6, 1), ilaclar=[Ilac(ad="Valsartan 160 mg")])
    assert "RECETE_RAPOR_KAPSAM" not in _kodlar(motor.calistir(r, rec, ks), "HATA")


def test_arb_diuretik_rapor_disinda_da_gecer(ks):
    r = _rapor(["Ramipril 5 mg"], "HT.")
    rec = Recete(
        tarih=date(2026, 6, 1),
        ilaclar=[Ilac(ad="Valsartan/Hidroklorotiyazid 160/12,5")],
    )
    assert "RECETE_RAPOR_KAPSAM" not in _kodlar(motor.calistir(r, rec, ks), "HATA")


def test_arb_kkb_rapor_disinda_hata_verir(ks):
    """ARB+KKB muaf değildir, kapsam kuralı yine çalışmalı."""
    r = _rapor(["Ramipril 5 mg"], "HT.")
    rec = Recete(
        tarih=date(2026, 6, 1),
        ilaclar=[Ilac(ad="Valsartan/Amlodipin 160/5 mg")],
    )
    assert "RECETE_RAPOR_KAPSAM" in _kodlar(motor.calistir(r, rec, ks), "HATA")
    