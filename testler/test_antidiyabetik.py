"""Antidiyabetik kural testleri."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sut import motor  # noqa: E402
from sut.semalar import Ilac, Rapor, Recete  # noqa: E402

KURAL_YOLU = Path(__file__).resolve().parents[1] / "kurallar" / "antidiyabetik.yaml"

SGLT2_IBARE = (
    "Metformin ve/veya sülfonilürelerin maksimum tolere edilebilir dozlarında "
    "yeterli glisemik kontrol sağlanamamış hastada."
)


@pytest.fixture(scope="module")
def ks():
    return motor.yukle(KURAL_YOLU)


def _kodlar(sonuc, seviye: str | None = None) -> set[str]:
    return {b.kural_id for b in sonuc.bulgular if seviye is None or b.seviye == seviye}


# --- SGLT-2 ibaresi: hem raporlu hem raporsuz aranır -------------------------

def test_sglt2_ibaresiz_hata(ks):
    r = Rapor(ilaclar=[Ilac(ad="Forziga 10 mg")], serbest_metin="Tip 2 DM.")
    assert "SGLT2_IBARE" in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_sglt2_raporda_ibare_varsa_hata_yok(ks):
    r = Rapor(ilaclar=[Ilac(ad="Forziga 10 mg")], serbest_metin=SGLT2_IBARE)
    assert "SGLT2_IBARE" not in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_sglt2_raporsuz_aciklamada_ibare_varsa_hata_yok(ks):
    rec = Recete(
        tarih=date(2026, 6, 1), ilaclar=[Ilac(ad="Jardiance 10 mg")],
        rapor_var=False, aciklama=SGLT2_IBARE,
    )
    assert "SGLT2_IBARE" not in _kodlar(motor.calistir(Rapor(), rec, ks), "HATA")


def test_sglt2_raporsuz_aciklama_bossa_hata(ks):
    rec = Recete(tarih=date(2026, 6, 1), ilaclar=[Ilac(ad="Jardiance 10 mg")], rapor_var=False)
    assert "SGLT2_IBARE" in _kodlar(motor.calistir(Rapor(), rec, ks), "HATA")


# --- DPP-4 ve uzun etkili insülin: aynı sınıftan birden fazla ürün olmaz ----

def test_iki_farkli_dpp4_hata(ks):
    r = Rapor(ilaclar=[Ilac(ad="Januvia 100 mg"), Ilac(ad="Trajenta 5 mg")])
    assert "DPP4_COKLU" in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_tek_dpp4_hata_yok(ks):
    r = Rapor(ilaclar=[Ilac(ad="Januvia 100 mg")])
    assert "DPP4_COKLU" not in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_lantus_levemir_birlikte_hata(ks):
    r = Rapor(ilaclar=[Ilac(ad="Lantus Solostar"), Ilac(ad="Levemir Flexpen")])
    assert "UZUN_INSULIN_COKLU" in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_tek_uzun_insulin_hata_yok(ks):
    r = Rapor(ilaclar=[Ilac(ad="Lantus Solostar")])
    assert "UZUN_INSULIN_COKLU" not in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_kisa_ve_uzun_insulin_birlikte_sorun_degil(ks):
    """Humalog (kısa) + Lantus (uzun) farklı sınıflardır, çakışmaz."""
    r = Rapor(ilaclar=[Ilac(ad="Humalog 100 U/ml"), Ilac(ad="Lantus Solostar")])
    sonuc = motor.calistir(r, None, ks)
    assert "UZUN_INSULIN_COKLU" not in _kodlar(sonuc, "HATA")
    assert "DPP4_COKLU" not in _kodlar(sonuc, "HATA")


# --- Ryzodeg / Toujeo raporsuz ödenmez --------------------------------------

def test_ryzodeg_raporsuz_hata(ks):
    rec = Recete(tarih=date(2026, 6, 1), ilaclar=[Ilac(ad="Ryzodeg Flextouch")], rapor_var=False)
    assert "OZEL_INSULIN_RAPORSUZ_YASAK" in _kodlar(motor.calistir(Rapor(), rec, ks), "HATA")


def test_toujeo_raporsuz_hata(ks):
    rec = Recete(tarih=date(2026, 6, 1), ilaclar=[Ilac(ad="Toujeo Solostar")], rapor_var=False)
    assert "OZEL_INSULIN_RAPORSUZ_YASAK" in _kodlar(motor.calistir(Rapor(), rec, ks), "HATA")


def test_ryzodeg_raporlu_bu_hata_yok(ks):
    r = Rapor(ilaclar=[Ilac(ad="Ryzodeg Flextouch")], serbest_metin="Uygun hasta.")
    assert "OZEL_INSULIN_RAPORSUZ_YASAK" not in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_lantus_raporsuz_bu_kural_tetiklenmez(ks):
    """Ryzodeg/Toujeo dışındaki insülinler raporsuz yasağına girmez."""
    rec = Recete(tarih=date(2026, 6, 1), ilaclar=[Ilac(ad="Lantus Solostar")], rapor_var=False)
    assert "OZEL_INSULIN_RAPORSUZ_YASAK" not in _kodlar(motor.calistir(Rapor(), rec, ks), "HATA")


# --- Byetta kombinasyon kuralları -------------------------------------------

def test_byetta_dpp4_birlikte_hata(ks):
    r = Rapor(ilaclar=[Ilac(ad="Byetta 10 mcg"), Ilac(ad="Januvia 100 mg")])
    assert "BYETTA_DPP4_CELISKI" in _kodlar(motor.calistir(r, None, ks), "HATA")


def test_byetta_sglt2_birlikte_bu_hata_yok(ks):
    """Byetta + SGLT2 izinli kombinasyon; yalnızca SGLT2 ibaresi istenir."""
    r = Rapor(
        ilaclar=[Ilac(ad="Byetta 10 mcg"), Ilac(ad="Jardiance 10 mg")],
        serbest_metin=SGLT2_IBARE,
    )
    sonuc = motor.calistir(r, None, ks)
    assert "BYETTA_DPP4_CELISKI" not in _kodlar(sonuc, "HATA")
    assert "SGLT2_IBARE" not in _kodlar(sonuc, "HATA")


# --- Metformin doz hatırlatması ---------------------------------------------

def test_metformin_bilgi_notu_verir(ks):
    r = Rapor(ilaclar=[Ilac(ad="Glifor 1000 mg")])
    assert "METFORMIN_DOZ_HATIRLATMA" in _kodlar(motor.calistir(r, None, ks), "BILGI")


def test_metformin_yoksa_bilgi_notu_yok(ks):
    r = Rapor(ilaclar=[Ilac(ad="Diamicron 60 mg")])
    assert "METFORMIN_DOZ_HATIRLATMA" not in _kodlar(motor.calistir(r, None, ks))


# --- Marka/etken madde tanıma ------------------------------------------------

@pytest.mark.parametrize(
    "ad, beklenen",
    [
        ("Janumet 50/1000 mg", {"DPP4", "METFORMIN"}),
        ("Galvus Met 50/1000", {"DPP4", "METFORMIN"}),
        ("Forziga 10 mg", {"SGLT2"}),
        ("Ryzodeg Flextouch", {"INSULIN_UZUN", "INSULIN_KISA"}),
        ("Diamicron MR 60 mg", {"SULFONILURE"}),
    ],
)
def test_sinif_tanima(ad, beklenen):
    from sut import ilac
    assert ilac.siniflari_bul(ad) == beklenen
