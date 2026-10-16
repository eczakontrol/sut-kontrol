"""SGK EK-4/A (bedeli ödenecek ilaçlar) barkod kataloğu.

Reçetede ilaç adının yanında yazan 13 haneli barkodu ürüne çevirir.
Barkod, marka adından çok daha güvenilirdir: yazım hatası olmaz.

Kayıt alanları:  k = SGK kamu kodu, a = ürün adı, e = etken madde (varsa).
Veri dosyası:    veri/katalog.json  (kaynak: EK-4/A listesi)
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

YOL = Path(__file__).resolve().parents[1] / "veri" / "katalog.json"
_BARKOD = re.compile(r"(?<!\d)\d{13}(?!\d)")
_KAMU_KODU = re.compile(r"\b[A-Za-z]\d{5}\b")


@lru_cache(maxsize=1)
def _yukle() -> dict:
    try:
        return json.loads(YOL.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


@lru_cache(maxsize=1)
def _kamu_kodu_indeksi() -> dict:
    """Kamu kodu (A10217 gibi) -> kayıt. Aynı kod birden fazla barkodda olabilir,
    ilk görülen tutulur (marka/doz farkı önemsiz, etken madde için yeterli)."""
    idx: dict[str, dict] = {}
    for kayit in _yukle().values():
        k = (kayit.get("k") or "").upper()
        idx.setdefault(k, kayit)
    return idx


def yuklu_mu() -> bool:
    return bool(_yukle())


def bul(barkod: str) -> dict | None:
    return _yukle().get(barkod)


def kamu_kodu_ile_bul(kamu_kodu: str) -> dict | None:
    return _kamu_kodu_indeksi().get((kamu_kodu or "").upper())


def barkodlari_bul(metin: str) -> list[str]:
    """Metinde geçen 13 haneli sayıları döndürür."""
    return _BARKOD.findall(metin or "")


def kamu_kodlarini_bul(metin: str) -> list[str]:
    """Metinde geçen SGK kamu kodlarını (A10217 gibi, harf+5 rakam) döndürür."""
    return [k.upper() for k in _KAMU_KODU.findall(metin or "")]
