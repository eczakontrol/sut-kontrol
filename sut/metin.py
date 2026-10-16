"""Türkçe metin normalizasyonu ve rapor ibaresi arama.

Bu modül projenin en sinsi hata kaynağını kapatır: Türkçe büyük/küçük harf
dönüşümü ve OCR'ın ı/i, ş/s, ğ/g karışmaları.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# Python'un varsayılan lower() metodu Türkçe için yanlıştır:
#   "I".lower()  -> "i"   (olması gereken: "ı")
#   "İ".lower()  -> "i̇"  (i + birleşik nokta, görünmez bir karakter daha)
# Bu yüzden önce elle çeviriyoruz.
_BUYUKTEN_KUCUGE = str.maketrans(
    {"I": "ı", "İ": "i", "Ş": "ş", "Ğ": "ğ", "Ü": "ü", "Ö": "ö", "Ç": "ç"}
)

# OCR ve yazım farklarını tolere etmek için aksanları sadeleştiriyoruz.
# "kan basıncı" ile "kan basinci" karşılaştırmada aynı hale gelir.
_SADELESTIRME = str.maketrans(
    {
        "ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c",
        "â": "a", "î": "i", "û": "u", "ā": "a", "ē": "e",
    }
)


def kucult(metin: str) -> str:
    """Türkçe kurallarına uygun küçük harfe çevirir."""
    return metin.translate(_BUYUKTEN_KUCUGE).lower()


def normalize(metin: str, sadelestir: bool = True) -> str:
    """Karşılaştırma için metni tekilleştirir.

    Küçük harfe çevirir, aksanları sadeleştirir, noktalamayı ve fazla
    boşlukları atar. Karşılaştırılan iki metin de bundan geçmelidir.
    """
    if not metin:
        return ""
    metin = unicodedata.normalize("NFC", metin)
    metin = kucult(metin)
    if sadelestir:
        metin = metin.translate(_SADELESTIRME)
    metin = re.sub(r"[^0-9a-z\s]", " ", metin)
    metin = re.sub(r"\s+", " ", metin)
    return metin.strip()


def _en_yakin_parca(hedef_norm: str, kalip_norm: str) -> tuple[float, str]:
    """Metin içinde kalıba en çok benzeyen kelime penceresini bulur.

    OCR bir iki harfi yanlış okuduğunda veya "monoterapi ile" yerine
    "monoterapiyle" yazıldığında doğrudan arama başarısız olur; bu fonksiyon
    kayan pencere ile benzerlik oranı hesaplayarak onu yakalar.
    """
    kelimeler = hedef_norm.split()
    kalip_uzunluk = len(kalip_norm.split())
    if not kelimeler or kalip_uzunluk == 0:
        return 0.0, ""

    en_iyi_oran, en_iyi_parca = 0.0, ""
    alt = max(1, kalip_uzunluk - 2)
    ust = min(len(kelimeler), kalip_uzunluk + 3)

    for genislik in range(alt, ust + 1):
        for i in range(0, len(kelimeler) - genislik + 1):
            parca = " ".join(kelimeler[i : i + genislik])
            oran = SequenceMatcher(None, kalip_norm, parca).ratio()
            if oran > en_iyi_oran:
                en_iyi_oran, en_iyi_parca = oran, parca

    return en_iyi_oran, en_iyi_parca


class IbareSonucu:
    """Bir ibarenin metinde bulunup bulunmadığının sonucu."""

    def __init__(self, bulundu: bool, oran: float, kanit: str = "", kalip: str = ""):
        self.bulundu = bulundu
        self.oran = oran
        self.kanit = kanit
        self.kalip = kalip

    def __repr__(self) -> str:
        return f"IbareSonucu(bulundu={self.bulundu}, oran={self.oran:.2f})"


def ibare_ara(metin: str, kaliplar: list[str], esik: float = 0.85) -> IbareSonucu:
    """Kalıplardan herhangi biri metinde geçiyor mu?

    Önce normalize edilmiş doğrudan arama yapar. Bulamazsa OCR gürültüsüne
    karşı benzerlik eşiği ile tekrar dener.
    """
    hedef = normalize(metin)
    if not hedef or not kaliplar:
        return IbareSonucu(False, 0.0)

    for kalip in kaliplar:
        kalip_norm = normalize(kalip)
        if kalip_norm and kalip_norm in hedef:
            return IbareSonucu(True, 1.0, kalip_norm, kalip)

    en_iyi_oran, en_iyi_parca, en_iyi_kalip = 0.0, "", ""
    for kalip in kaliplar:
        oran, parca = _en_yakin_parca(hedef, normalize(kalip))
        if oran > en_iyi_oran:
            en_iyi_oran, en_iyi_parca, en_iyi_kalip = oran, parca, kalip

    return IbareSonucu(en_iyi_oran >= esik, en_iyi_oran, en_iyi_parca, en_iyi_kalip)
