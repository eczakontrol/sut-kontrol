"""Barkod kataloğu testleri."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sut import ilac, katalog, motor  # noqa: E402
from sut.semalar import Ilac, Rapor  # noqa: E402

KURAL_YOLU = Path(__file__).resolve().parents[1] / "kurallar" / "antihipertansif.yaml"


@pytest.fixture(scope="module")
def ks():
    return motor.yukle(KURAL_YOLU)


def test_katalog_yuklu_ve_dolu():
    assert katalog.yuklu_mu()
    assert len(katalog._yukle()) > 8000


def test_katalog_anahtarlari_13_haneli():
    assert all(len(k) == 13 and k.isdigit() for k in katalog._yukle())


@pytest.mark.parametrize(
    "metin, beklenen",
    [
        ("Bilinmeyen Urun (8699504091199)", {"ARB", "KKB"}),          # Exforge 5/160
        ("DIOVAN 160 MG 28 FTB (8699504090758)", {"ARB"}),
        ("COSIMPREL 5 MG/10 MG (8699552090922)", {"ACE", "BETA"}),    # KKB DEĞİL
        ("NORMOTRI 5 MG (8699543091884)", {"ACE", "KKB", "DIURETIK"}),
        ("ATORVASTATIN 20 MG (8690000000012)", set()),                # katalogda yok
        ("Ilac 86995040911990", set()),                               # 14 hane barkod sayılmaz
    ],
)
def test_barkoddan_sinif(metin, beklenen):
    assert ilac.siniflari_bul(metin) == beklenen


def test_barkodla_yazilan_kombinasyon_ibare_ister(ks):
    r = Rapor(
        duzenleme_tarihi=date(2026, 1, 1),
        bitis_tarihi=date(2027, 12, 31),
        ilaclar=[Ilac(ad="ILAC (8699504091199)")],
        serbest_metin="Esansiyel hipertansiyon.",
    )
    hatalar = {b.kural_id for b in motor.calistir(r, None, ks).bulgular if b.seviye == "HATA"}
    assert "ARB_KKB_MONOTERAPI" in hatalar


@pytest.mark.parametrize(
    "metin, beklenen",
    [
        ("BILINMEYEN ILAC (A10217)", {"ARB", "KKB"}),   # Exforge'un kamu kodu
        ("ILAC A99999", set()),                          # katalogda olmayan kod
    ],
)
def test_kamu_koduyla_sinif(metin, beklenen):
    assert ilac.siniflari_bul(metin) == beklenen
