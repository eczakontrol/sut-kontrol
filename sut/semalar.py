"""Veri modelleri.

Bu şema, görüntüyü okuyan katman ile kuralları çalıştıran katman
arasındaki sözleşmedir. OCR'ı değiştirseniz kurallar bozulmaz,
kural eklerseniz OCR'a dokunmanız gerekmez.

Okunamayan her alan None kalır. Boş bırakmak, uydurmaktan iyidir.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from . import ilac

Seviye = Literal["HATA", "UYARI", "BILGI"]


class Ilac(BaseModel):
    ad: str
    barkod: str | None = None
    adet: int | None = None
    kullanim_sekli: str | None = None

    @property
    def siniflar(self) -> set[str]:
        return ilac.siniflari_bul(self.ad)

    @property
    def etken_maddeler(self) -> dict[str, str]:
        return ilac.maddeleri_bul(self.ad)


class Rapor(BaseModel):
    rapor_no: str | None = None
    duzenleme_tarihi: date | None = None
    bitis_tarihi: date | None = None
    rapor_tipi: str | None = None          # "uzman hekim" / "sağlık kurulu"
    rapor_kodlari: list[str] = Field(default_factory=list)  # Örn: ["04.05", "20.00"] (SGK EK-4/D Rapor Kodu)
    tani_kodlari: list[str] = Field(default_factory=list)   # Örn: ["I10", "E11.9", "N40"] (ICD-10 Alt Tanı Kodu)
    hekim_branslari: list[str] = Field(default_factory=list)
    ilaclar: list[Ilac] = Field(default_factory=list)

    # Raporun serbest metin alanlarının tamamı. Aranan ibareler burada olur.
    serbest_metin: str = ""

    # --- STATİN / LDL / OSTEOPOROZ / PROSTAT ALANLARI ---
    idame_mi: bool = False
    ldl_degeri: float | None = None
    ldl_tarihi: date | None = None
    ldl_degeri_2: float | None = None
    ldl_tarihi_2: date | None = None
    risk_faktorleri: list[str] = Field(default_factory=list)
    t_skoru: float | None = None
    hasta_yasi: int | None = None
    hipertansiyon_eslik_ediyor: bool | None = None


class Recete(BaseModel):
    recete_no: str | None = None
    tarih: date | None = None
    hekim_bransi: str | None = None
    tani_kodlari: list[str] = Field(default_factory=list)
    ilaclar: list[Ilac] = Field(default_factory=list)
    rapor_var: bool = True                 # False: raporsuz reçete
    aciklama: str = ""                     # reçete açıklaması (ibare buradan aranır)
    arb_kutu_adedi: int | None = None      # ARB içeren ürünlerin toplam kutu sayısı


class Bulgu(BaseModel):
    kural_id: str
    seviye: Seviye
    baslik: str
    mesaj: str
    sut_madde: str | None = None
    kanit: str | None = None          # metinde bulunan/bulunamayan parça
    guven: float | None = None        # ibare eşleşme oranı

    @property
    def simge(self) -> str:
        return {"HATA": "✕", "UYARI": "!", "BILGI": "i"}[self.seviye]


class Sonuc(BaseModel):
    bulgular: list[Bulgu] = Field(default_factory=list)
    kural_seti_surumu: str = ""

    @property
    def hatalar(self) -> list[Bulgu]:
        return [b for b in self.bulgular if b.seviye == "HATA"]

    @property
    def uyarilar(self) -> list[Bulgu]:
        return [b for b in self.bulgular if b.seviye == "UYARI"]

    @property
    def gecerli(self) -> bool:
        return not self.hatalar