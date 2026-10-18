"""Kural motoru.

Kurallar YAML'dan okunur, burada çalıştırılır. Motorun kendisi hiçbir
SUT bilgisi içermez -- o bilgi kurallar/ klasöründe durur. Bu ayrım
sayesinde SUT değiştiğinde kod değil veri güncellenir.

Kapsam kavramı
--------------
Her kural ya tek bir ilaç ürününe ("urun") ya da rapordaki/reçetedeki
tüm ilaçların oluşturduğu havuza ("tumu") bakar. Bu ayrım kritik:
ARB + KKB kombinasyon ürünü ile ayrı ayrı yazılmış ARB ve KKB kutuları
SUT açısından farklı şeylerdir.

Birden fazla kural dosyası (antihipertansif, antidiyabetik, ...) olabilir;
her biri ayrı bir KuralSeti olarak yüklenip aynı rapor/reçete üzerinde ayrı
ayrı çalıştırılır (bkz. app.py). Bu dosya tek bir kural setini çalıştırır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import ilac
from .metin import ibare_ara, normalize
from .semalar import Bulgu, Ilac, Rapor, Recete, Sonuc


@dataclass
class KuralSeti:
    surum: str
    kaynak: str
    ayarlar: dict
    ibareler: dict
    kurallar: list[dict]


def yukle(yol: str | Path) -> KuralSeti:
    veri = yaml.safe_load(Path(yol).read_text(encoding="utf-8"))
    return KuralSeti(
        surum=str(veri.get("surum", "")),
        kaynak=veri.get("kaynak", ""),
        ayarlar=veri.get("ayarlar", {}),
        ibareler=veri.get("ibareler", {}),
        kurallar=veri.get("kurallar", []),
    )


def _gruplar(havuz: list[Ilac], kapsam: str) -> list[tuple[str, set[str]]]:
    """Kuralın bakacağı (etiket, sınıf kümesi) çiftlerini üretir."""
    if not havuz:
        return []
    if kapsam == "tumu":
        etiket = " + ".join(i.ad for i in havuz)
        return [(etiket, ilac.siniflari_bul(etiket))]
    return [(i.ad, i.siniflar) for i in havuz]


def _tetiklendi_mi(tetikleyici: dict, siniflar: set[str]) -> bool:
    hepsi = set(tetikleyici.get("hepsi_bulunmali", []))
    herhangi = set(tetikleyici.get("herhangi_bulunmali", []))
    hicbiri = set(tetikleyici.get("hicbiri_bulunmamali", []))

    if hepsi and not hepsi.issubset(siniflar):
        return False
    if herhangi and not (herhangi & siniflar):
        return False
    if hicbiri & siniflar:
        return False
    return bool(hepsi or herhangi)


# Olumsuzluk kökleri (normalize edilmiş metinde aranır).
# "alınamamıştır", "alınmadığı", "sağlanamamıştır" gibi biçimleri yakalar.
OLUMSUZLUK_KOKLERI = (
    "alinamam", "alinamad", "alinmad", "alinmam",
    "saglanamam", "saglanamad", "saglanmad", "saglanmam",
)


def _olumsuz_mu(cumle: str | None) -> bool:
    """Eşleşen cümlede 'kontrol altına alınamadı' anlamı var mı?"""
    n = normalize(cumle or "")
    return any(kok in n for kok in OLUMSUZLUK_KOKLERI)


def _ibare_kurali(kural: dict, ks: KuralSeti, rapor: Rapor, etiket: str) -> Bulgu:
    tanim = ks.ibareler.get(kural["ibare"], {})
    sonuc = ibare_ara(
        rapor.serbest_metin,
        tanim.get("kaliplar", []),
        esik=float(tanim.get("esik", 0.85)),
    )

    # 1) Benzer cümle bulundu ama olumsuzluk yok ("alınmıştır" gibi) -> HATA
    if sonuc.bulundu and not _olumsuz_mu(sonuc.kanit):
        return Bulgu(
            kural_id=kural["id"],
            seviye=kural.get("seviye", "HATA"),
            baslik=kural["baslik"],
            mesaj=kural["mesaj_yok"].strip()
            + " Raporda benzer bir cümle var ama olumsuzluk içermiyor "
            "(kan basıncının kontrol altında olduğunu söylüyor olabilir).",
            sut_madde=kural.get("sut_madde"),
            kanit=f"Bulunan cümle: {sonuc.kanit}",
            guven=round(sonuc.oran, 3),
        )

    # 2) İbare bulundu ve olumsuzluk var -> BİLGİ
    if sonuc.bulundu:
        return Bulgu(
            kural_id=kural["id"],
            seviye="BILGI",
            baslik=kural["baslik"],
            mesaj=kural.get("mesaj_var", "İbare bulundu.").strip(),
            sut_madde=kural.get("sut_madde"),
            kanit=sonuc.kanit or None,
            guven=round(sonuc.oran, 3),
        )

    # 3) İbare hiç yok -> HATA
    return Bulgu(
        kural_id=kural["id"],
        seviye=kural.get("seviye", "HATA"),
        baslik=kural["baslik"],
        mesaj=kural["mesaj_yok"].strip(),
        sut_madde=kural.get("sut_madde"),
        kanit=f"Tetikleyen ürün: {etiket}",
        guven=round(sonuc.oran, 3),
    )


def _ayrik_urun_kurali(kural: dict, havuz: list[Ilac]) -> list[Bulgu]:
    """Hedef sınıflar havuzda var ama hiçbir tek üründe birlikte değilse not düşer."""
    hedef = set(kural.get("siniflar", []))
    if not hedef or not havuz:
        return []

    havuzda: set[str] = set()
    for i in havuz:
        havuzda |= i.siniflar
    if not hedef.issubset(havuzda):
        return []

    for i in havuz:
        if hedef.issubset(i.siniflar):
            return []          # kombinasyon ürünü zaten var, not gereksiz

    tasiyicilar = [i.ad for i in havuz if i.siniflar & hedef]
    return [
        Bulgu(
            kural_id=kural["id"],
            seviye=kural.get("seviye", "BILGI"),
            baslik=kural["baslik"],
            mesaj=kural["mesaj"].strip(),
            sut_madde=kural.get("sut_madde"),
            kanit="Ayrı ürünler: " + ", ".join(tasiyicilar),
        )
    ]


def _kapsam_kurali(kural: dict, rapor: Rapor, recete: Recete | None) -> list[Bulgu]:
    if recete is None or not rapor.ilaclar:
        return []
    rapor_maddeleri: set[str] = set()
    for i in rapor.ilaclar:
        rapor_maddeleri |= set(i.etken_maddeler)

    # SUT'a göre raporsuz da yazılabilen sınıf kombinasyonları (ör. ARB tek
    # başına, ARB+diüretik). Bunlar başka bir rapora bağlı olmak zorunda değil.
    muaf = [frozenset(s) for s in kural.get("muaf_siniflar", [])]

    bulgular: list[Bulgu] = []
    for r_ilac in recete.ilaclar:
        maddeler = set(r_ilac.etken_maddeler)
        if not maddeler:
            continue
        if frozenset(r_ilac.siniflar) in muaf:
            continue  # raporsuz da yazılabilen grup, kapsam aranmaz
        if not maddeler.issubset(rapor_maddeleri):
            eksik = ", ".join(sorted(maddeler - rapor_maddeleri))
            bulgular.append(
                Bulgu(
                    kural_id=kural["id"],
                    seviye=kural.get("seviye", "HATA"),
                    baslik=kural["baslik"],
                    mesaj=f"Reçetedeki '{r_ilac.ad}' raporda yer almıyor.",
                    sut_madde=kural.get("sut_madde"),
                    kanit=f"Raporda bulunmayan etken madde: {eksik}",
                )
            )
    return bulgular


def _raporsuz_recete_kurali(kural: dict, ks: KuralSeti, recete: Recete | None) -> list[Bulgu]:
    """Raporsuz ARB reçetesi: ayda en fazla 1 kutu,
    ARB+KKB içeren üründe reçete açıklamasında monoterapi ibaresi.
    Hekim branşı kontrol edilmez (uzman hekim de yazabilir)."""
    if recete is None or recete.rapor_var:
        return []
    arb_urunleri = [i for i in recete.ilaclar if "ARB" in i.siniflar]
    if not arb_urunleri:
        return []

    sut = kural.get("sut_madde")
    etiket = ", ".join(i.ad for i in arb_urunleri)
    bulgular: list[Bulgu] = []

    azami = int(kural.get("azami_kutu", 1))
    if recete.arb_kutu_adedi is None:
        bulgular.append(Bulgu(
            kural_id=kural["id"] + "_KUTU", seviye="UYARI",
            baslik="Raporsuz reçetede kutu sayısı girilmemiş",
            mesaj=f"Raporsuz ARB reçetesinde ayda en fazla {azami} kutu yazılabilir. "
                  "Kutu sayısını girin.",
            sut_madde=sut, kanit=f"Tetikleyen ürün: {etiket}",
        ))
    elif recete.arb_kutu_adedi > azami:
        bulgular.append(Bulgu(
            kural_id=kural["id"] + "_KUTU", seviye=kural.get("seviye", "HATA"),
            baslik="Raporsuz ARB reçetesinde kutu sınırı aşılmış",
            mesaj=f"Raporsuz ARB reçetesinde ayda en fazla {azami} kutu yazılabilir.",
            sut_madde=sut,
            kanit=f"Girilen kutu sayısı: {recete.arb_kutu_adedi} · Tetikleyen ürün: {etiket}",
        ))

    kombine = [i.ad for i in arb_urunleri if "KKB" in i.siniflar]
    if kombine:
        ibare_kurali = {
            "id": kural["id"] + "_IBARE",
            "baslik": "Raporsuz ARB + KKB reçetesinde monoterapi ibaresi",
            "ibare": kural["ibare"],
            "seviye": kural.get("seviye", "HATA"),
            "sut_madde": sut,
            "mesaj_yok": (
                "Raporsuz reçetede ARB + KKB içeren ürün var. Reçete açıklamasında "
                "hastanın monoterapi ile kan basıncının yeterli oranda kontrol altına "
                "alınamadığı belirtilmelidir; bu ibare tespit edilemedi."
            ),
            "mesaj_var": "Reçete açıklamasında gereken monoterapi ibaresi mevcut.",
        }
        bulgular.append(
            _ibare_kurali(ibare_kurali, ks, Rapor(serbest_metin=recete.aciklama), ", ".join(kombine))
        )
    return bulgular


def _tarih_kurali(kural: dict, rapor: Rapor, recete: Recete | None) -> list[Bulgu]:
    if recete is None or recete.tarih is None:
        return []
    sorunlar: list[str] = []
    if rapor.duzenleme_tarihi and recete.tarih < rapor.duzenleme_tarihi:
        sorunlar.append(
            f"reçete tarihi rapor düzenleme tarihinden ({rapor.duzenleme_tarihi}) önce"
        )
    if rapor.bitis_tarihi and recete.tarih > rapor.bitis_tarihi:
        sorunlar.append(
            f"reçete tarihi rapor bitiş tarihinden ({rapor.bitis_tarihi}) sonra"
        )
    if not sorunlar:
        return []
    return [
        Bulgu(
            kural_id=kural["id"],
            seviye=kural.get("seviye", "HATA"),
            baslik=kural["baslik"],
            mesaj="Rapor bu reçeteyi kapsamıyor: " + "; ".join(sorunlar) + ".",
            sut_madde=kural.get("sut_madde"),
            kanit=f"Reçete tarihi: {recete.tarih}",
        )
    ]


def _tekil_sinif_kurali(kural: dict, havuz: list[Ilac]) -> list[Bulgu]:
    """Aynı sınıftan birden fazla FARKLI ETKEN MADDE varsa uyarır (ürün/satır
    sayısına değil, distinct etken madde sayısına bakılır -- "Lantus Solostar
    + Levemir Flexpen" aynı satıra yazılsa bile yakalanır)."""
    sinif = kural.get("sinif")
    azami = int(kural.get("azami_urun", 1))
    if not sinif:
        return []
    etken_maddeler: set[str] = set()
    urunler: list[str] = []
    for i in havuz:
        for ad, s in i.etken_maddeler.items():
            if s == sinif:
                etken_maddeler.add(ad)
                if i.ad not in urunler:
                    urunler.append(i.ad)
    if len(etken_maddeler) <= azami:
        return []
    return [
        Bulgu(
            kural_id=kural["id"],
            seviye=kural.get("seviye", "HATA"),
            baslik=kural["baslik"],
            mesaj=kural["mesaj"].strip(),
            sut_madde=kural.get("sut_madde"),
            kanit="Birlikte yazılan ürünler: " + ", ".join(urunler),
        )
    ]


_TIP2DM_DESENI = re.compile(r"tip\s*-?\s*2\s*(dm|diyabet)")


def _tani_kodu_ibare_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    """Belirli tanı kodu önekleri (ör. E12/E13/E14) + belirli ilaç sınıfı varsa,
    rapor ya da reçete metninde sabit bir ifade (ör. "Tip-2 DM") aranır.
    Kısa anahtar kelime olduğu için bulanık cümle eşleştirmesi yerine doğrudan
    desen araması yapılır."""
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(havuz, kural.get("kapsam", "urun"))
    tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(tetikleyici, s)]
    if not tetikleyen:
        return []

    onekler = tuple(k.upper() for k in kural.get("tani_onekleri", []))
    if not onekler:
        return []
    eslesen = [t for t in (rapor.tani_kodlari or []) if t.upper().startswith(onekler)]
    if not eslesen:
        return []

    etiket = ", ".join(tetikleyen)
    birlesik = normalize((rapor.serbest_metin or "") + " " + ((recete.aciklama if recete else "") or ""))
    if _TIP2DM_DESENI.search(birlesik):
        return [
            Bulgu(
                kural_id=kural["id"], seviye="BILGI", baslik=kural["baslik"],
                mesaj=kural.get("mesaj_var", "Gereken ifade mevcut.").strip(),
                sut_madde=kural.get("sut_madde"),
                kanit=f"Tanı kodu: {', '.join(eslesen)} · Tetikleyen ürün: {etiket}",
            )
        ]
    return [
        Bulgu(
            kural_id=kural["id"], seviye=kural.get("seviye", "HATA"), baslik=kural["baslik"],
            mesaj=kural["mesaj_yok"].strip(), sut_madde=kural.get("sut_madde"),
            kanit=f"Tanı kodu: {', '.join(eslesen)} · Tetikleyen ürün: {etiket}",
        )
    ]


def _cok_kaynakli_ibare_kurali(
    kural: dict, ks: KuralSeti, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]
) -> list[Bulgu]:
    """İbareyi hem rapor hem reçete açıklamasında arar (hangisinde varsa yeter).
    Raporlu/raporsuz ayrımı yapmaz -- bazı SUT maddelerinde ibare her durumda gerekir."""
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(havuz, kural.get("kapsam", "urun"))
    tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(tetikleyici, s)]
    if not tetikleyen:
        return []
    etiket = ", ".join(tetikleyen)

    birlesik_metin = (rapor.serbest_metin or "") + "\n" + ((recete.aciklama if recete else "") or "")
    gecici_rapor = Rapor(serbest_metin=birlesik_metin)
    return [_ibare_kurali(kural, ks, gecici_rapor, etiket)]


def _raporsuz_yasakli_urun_kurali(kural: dict, recete: Recete | None) -> list[Bulgu]:
    """Belirli markalar (ör. Ryzodeg, Toujeo) raporsuz kesinlikle ödenmez."""
    if recete is None or recete.rapor_var:
        return []
    anahtarlar = [normalize(a) for a in kural.get("markalar", [])]
    if not anahtarlar:
        return []
    bulgular: list[Bulgu] = []
    for i in recete.ilaclar:
        ad_norm = normalize(i.ad)
        for a in anahtarlar:
            if re.search(rf"\b{re.escape(a)}\b", ad_norm):
                bulgular.append(
                    Bulgu(
                        kural_id=kural["id"],
                        seviye=kural.get("seviye", "HATA"),
                        baslik=kural["baslik"],
                        mesaj=kural["mesaj"].strip(),
                        sut_madde=kural.get("sut_madde"),
                        kanit=f"Tetikleyen ürün: {i.ad}",
                    )
                )
                break
    return bulgular


def _brans_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    """Rapor varsa raporu çıkaran hekimin branşı, raporsuzsa reçeteyi yazan
    hekimin branşı kontrol edilir (SUT'un "bu hekimlerin raporuna dayanarak
    tüm hekimlerce reçete edilebilir" mantığı)."""
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(havuz, kural.get("kapsam", "urun"))
    tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(tetikleyici, s)]
    if not tetikleyen:
        return []
    etiket = ", ".join(tetikleyen)
    izinli = [normalize(b) for b in kural.get("izinli_branslar", [])]

    def izinli_mi(brans: str) -> bool:
        b = normalize(brans)
        return any(i in b for i in izinli)

    raporsuz = recete is not None and not recete.rapor_var

    if raporsuz:
        brans = recete.hekim_bransi
        if not brans:
            return [
                Bulgu(
                    kural_id=kural["id"], seviye="UYARI", baslik=kural["baslik"],
                    mesaj="Raporsuz reçetede hekim branşı girilmemiş. "
                          + kural.get("mesaj_brans_yok", "").strip(),
                    sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen ürün: {etiket}",
                )
            ]
        if not izinli_mi(brans):
            return [
                Bulgu(
                    kural_id=kural["id"], seviye=kural.get("seviye", "HATA"),
                    baslik=kural["baslik"], mesaj=kural["mesaj_yok"].strip(),
                    sut_madde=kural.get("sut_madde"),
                    kanit=f"Reçeteyi yazan branş: {brans} · Tetikleyen ürün: {etiket}",
                )
            ]
        return []

    branslar = rapor.hekim_branslari or []
    if not branslar:
        return [
            Bulgu(
                kural_id=kural["id"], seviye="UYARI", baslik=kural["baslik"],
                mesaj="Rapor hekim branşı girilmemiş; raporu çıkaran hekimin branşını kontrol edin.",
                sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen ürün: {etiket}",
            )
        ]
    if not any(izinli_mi(b) for b in branslar):
        return [
            Bulgu(
                kural_id=kural["id"], seviye=kural.get("seviye", "HATA"),
                baslik=kural["baslik"], mesaj=kural["mesaj_yok"].strip(),
                sut_madde=kural.get("sut_madde"),
                kanit=f"Rapor branşı: {', '.join(branslar)} · Tetikleyen ürün: {etiket}",
            )
        ]
    return []


def _doz_bul(urun_adi: str) -> float | None:
    """Ürün adından miligram değerini (ör. '20 mg', '145.5 mg') çeker."""
    eslesme = re.search(r"(\d+(?:[.,]\d+)?)\s*mg", urun_adi, re.IGNORECASE)
    if eslesme:
        return float(eslesme.group(1).replace(",", "."))
    return None

def _doz_siniri_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    """Belirli etken maddeler için miligram doz eşiğini ve branş kısıtını kontrol eder."""
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(havuz, "urun")
    
    hedef_madde = tetikleyici.get("herhangi_bulunmali", [""])[0]
    tetikleyen_urunler = [e for e, s in gruplar if hedef_madde in s]
    
    if not tetikleyen_urunler:
        return []

    min_doz = float(kural.get("min_doz", 999))
    izinli = [normalize(b) for b in kural.get("izinli_branslar", [])]
    
    def izinli_mi(brans: str) -> bool:
        b = normalize(brans)
        return any(i in b for i in izinli)

    bulgular = []
    for urun in tetikleyen_urunler:
        doz = _doz_bul(urun)
        if doz is None or doz < min_doz:
            continue # Doz eşiğin altındaysa bu kurala takılmaz
            
        # Yüksek doz statin raporsuz ÖDENMEZ.
        raporsuz = recete is not None and not recete.rapor_var
        if raporsuz:
            bulgular.append(
                Bulgu(
                    kural_id=kural["id"], seviye="HATA", baslik=kural["baslik"],
                    mesaj=f"Yüksek doz statin ({min_doz} mg ve üzeri) raporsuz ödenmez.",
                    sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen ürün: {urun} (Okunan doz: {doz} mg)"
                )
            )
            continue
            
        # Raporluysa, raporu çıkaran branş kontrol edilir.
        branslar = rapor.hekim_branslari or []
        if not branslar:
            bulgular.append(
                Bulgu(
                    kural_id=kural["id"], seviye="UYARI", baslik=kural["baslik"],
                    mesaj=f"Rapor hekim branşı girilmemiş. {min_doz} mg ve üzeri doz için rapor branşı kontrol edilmeli.",
                    sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen ürün: {urun}"
                )
            )
            continue
            
        if not any(izinli_mi(b) for b in branslar):
            bulgular.append(
                Bulgu(
                    kural_id=kural["id"], seviye="HATA", baslik=kural["baslik"],
                    mesaj=kural["mesaj_yok"].strip(),
                    sut_madde=kural.get("sut_madde"),
                    kanit=f"Rapor branşı: {', '.join(branslar)} · Tetikleyen ürün: {urun} (Okunan doz: {doz} mg)"
                )
            )
            
    return bulgular


def _ldl_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    """Statinler için LDL ve Risk Faktörü kriterlerini denetler."""
    tetikleyici = kural.get("tetikleyici", {})
    hedef_maddeler = tetikleyici.get("herhangi_bulunmali", [])
    
    tetikleyen_urunler = []
    for e, s in _gruplar(havuz, "urun"):
        if any(madde in s for madde in hedef_maddeler):
            tetikleyen_urunler.append(e)
            
    if not tetikleyen_urunler:
        return []
        
    etiket = ", ".join(tetikleyen_urunler)
    bulgular = []
    
    # 1. İDAME RAPOR KONTROLÜ
    if rapor.idame_mi:
        if rapor.ldl_degeri is None:
            # İdame raporda ilk LDL yazmıyorsa HATA ver!
            bulgular.append(Bulgu(
                kural_id=kural["id"]+"_IDAME_EKS", 
                seviye="HATA", 
                baslik="Eksik Bilgi (İdame Rapor)", 
                mesaj="SUT kuralı gereği; idame (yenileme) raporlarında hastanın tedaviye İLK BAŞLADIĞI tarihteki LDL değeri ve tahlil tarihi raporda MUTLAKA belirtilmelidir. Raporda başlangıç LDL değeri tespit edilemedi.", 
                sut_madde=kural.get("sut_madde"), 
                kanit=f"Tetikleyen: {etiket}"
            ))
        else:
            # İlk LDL yazıyorsa BİLGİ ver ve 6 ay kuralını hatırlat
            bulgular.append(Bulgu(
                kural_id=kural["id"]+"_IDAME_OK", 
                seviye="BILGI", 
                baslik="İdame Rapor Kriterleri", 
                mesaj="İdame rapor seçildi ve başlangıç LDL değeri mevcut. DİKKAT: Hastanın tedaviye 6 aydan uzun süre ara vermediğinden emin olmak için Medula İlaç Geçmişi'ni kontrol edin (Ara verildiyse yandaki '6 aydan fazla ara verilmiş' kutusunu işaretleyin).", 
                sut_madde=kural.get("sut_madde"), 
                kanit=f"Başlangıç LDL: {rapor.ldl_degeri} | Tetikleyen: {etiket}"
            ))
        return bulgular
        
    if rapor.ldl_degeri is None:
        bulgular.append(Bulgu(kural_id=kural["id"]+"_LDL_EKS", seviye="UYARI", baslik="LDL Değeri Eksik", mesaj="İlk raporlarda tahlildeki LDL değeri girilmelidir.", sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen: {etiket}"))
        return bulgular
        
    ldl = rapor.ldl_degeri
    
    # İki tahlil kuralı (En az 7 gün ara ve düşük olan LDL'nin baz alınması)
    iki_tahlil = False
    if rapor.ldl_degeri_2 is not None and rapor.ldl_tarihi_2 is not None and rapor.ldl_tarihi is not None:
        gun_farki = abs((rapor.ldl_tarihi - rapor.ldl_tarihi_2).days)
        if gun_farki >= 7:
            iki_tahlil = True
            ldl = min(rapor.ldl_degeri, rapor.ldl_degeri_2) 
        else:
            bulgular.append(Bulgu(kural_id=kural["id"]+"_GUN_FARKI", seviye="HATA", baslik="Tahlil Süresi Yetersiz", mesaj="İki LDL tahlili arasında en az 7 gün (1 hafta) olmalıdır.", sut_madde=kural.get("sut_madde"), kanit=f"Fark: {gun_farki} gün"))
            return bulgular
    
    if rapor.ldl_tarihi and rapor.duzenleme_tarihi:
        if (rapor.duzenleme_tarihi - rapor.ldl_tarihi).days > 185:
            bulgular.append(Bulgu(kural_id=kural["id"]+"_TARIH", seviye="HATA", baslik="Tahlil Tarihi Eski", mesaj="Tahlil tarihi, rapor düzenleme tarihinden en fazla 6 ay önce olabilir.", sut_madde=kural.get("sut_madde"), kanit=f"Tahlil: {rapor.ldl_tarihi.strftime('%d.%m.%Y')}"))
            return bulgular
    elif not rapor.ldl_tarihi:
        bulgular.append(Bulgu(kural_id=kural["id"]+"_TAR_EKS", seviye="UYARI", baslik="Tahlil Tarihi Eksik", mesaj="6 aylık geçerlilik süresinin kontrolü için tahlil tarihini girin.", sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen: {etiket}"))
        
    riskler = rapor.risk_faktorleri or []
    yuksek_risk_listesi = ["Diyabet (Diabetes Mellitus)", "Geçirilmiş MI / Akut Koroner Sendrom", "Geçirilmiş İnme", "Koroner Arter Hastalığı (KAH)", "Periferik Arter Hastalığı (PAH)", "Abdominal Aort Anevrizması", "Karotis Arter Hastalığı"]
    ek_risk_listesi = ["Hipertansiyon", "Ailede erken kardiyovasküler hastalık öyküsü", "65 yaş ve üzeri"]
    
    hastadaki_yuksek = [r for r in riskler if r in yuksek_risk_listesi]
    hastadaki_ek = [r for r in riskler if r in ek_risk_listesi]
    ek_sayi = len(hastadaki_ek)
    
    if hastadaki_yuksek:
        if ldl > 70:
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="BILGI", baslik="LDL > 70 ve Yüksek Risk", mesaj="Yüksek riskli hastalık mevcut. Tek tahlil yeterlidir.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl} | Hastalık: {', '.join(hastadaki_yuksek)}"))
        else:
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik="LDL Kriteri Sağlanmadı", mesaj="Yüksek riskli hastalıklarda tedaviye başlamak için LDL değeri 70'in üzerinde olmalıdır.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl}"))
    elif ldl > 190:
         if iki_tahlil:
            bulgular.append(Bulgu(kural_id=kural["id"], seviye="BILGI", baslik="LDL > 190", mesaj="LDL 190'ın üzerinde ve en az 1 hafta arayla 2 tahlil mevcut. Ek risk faktörü aranmaz.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl}"))
         else:
             bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik="Eksik Tahlil (LDL > 190)", mesaj="LDL 190'ın üzerinde olduğunda ek risk faktörü aranmaz ANCAK en az 1 hafta ara ile yapılmış 2 adet LDL tahlili gereklidir.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl} | 2 Tahlil: Yok"))
    elif ldl > 160:
         if ek_sayi >= 2 and iki_tahlil:
             bulgular.append(Bulgu(kural_id=kural["id"], seviye="BILGI", baslik="LDL > 160", mesaj="LDL 160 üzerinde, en az 2 ek risk faktörü ve 1 hafta aralıklı 2 tahlil mevcut.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl} | Riskler: {', '.join(hastadaki_ek)}"))
         elif ek_sayi < 2:
             bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik="Yetersiz Ek Risk Faktörü", mesaj="LDL 160-190 arasında iken en az 2 ek risk faktörü gereklidir.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl} | Girilen: {ek_sayi}"))
         else:
             bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik="Eksik Tahlil (LDL > 160)", mesaj="LDL 160-190 arasında iken en az 1 hafta ara ile yapılmış 2 adet LDL tahlili gereklidir.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl} | 2 Tahlil: Yok"))
    elif ldl > 130:
         if ek_sayi >= 3 and iki_tahlil:
             bulgular.append(Bulgu(kural_id=kural["id"], seviye="BILGI", baslik="LDL > 130", mesaj="LDL 130 üzerinde, en az 3 ek risk faktörü ve 1 hafta aralıklı 2 tahlil mevcut.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl} | Riskler: {', '.join(hastadaki_ek)}"))
         elif ek_sayi < 3:
             bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik="Yetersiz Ek Risk Faktörü", mesaj="LDL 130-160 arasında iken en az 3 ek risk faktörü gereklidir.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl} | Girilen: {ek_sayi}"))
         else:
             bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik="Eksik Tahlil (LDL > 130)", mesaj="LDL 130-160 arasında iken en az 1 hafta ara ile yapılmış 2 adet LDL tahlili gereklidir.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl} | 2 Tahlil: Yok"))
    else:
         bulgular.append(Bulgu(kural_id=kural["id"], seviye="HATA", baslik="LDL Kriteri Sağlanmadı", mesaj="LDL değeri 130'un altında ve hastada yüksek riskli bir hastalık yok. SUT kriterleri karşılanmıyor.", sut_madde=kural.get("sut_madde"), kanit=f"LDL: {ldl}"))
         
    return bulgular

def _tani_kodu_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    """Belirli ilaç grupları için SUT'un zorunlu kıldığı ICD-10 tanı kodlarını denetler."""
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(havuz, "urun")
    tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(tetikleyici, s)]
    
    if not tetikleyen:
        return []
        
    etiket = ", ".join(tetikleyen)
    beklenen_kodlar = tuple(k.upper() for k in kural.get("zorunlu_kodlar", []))
    
    if not beklenen_kodlar:
        return []
        
    rapordaki_kodlar = rapor.tani_kodlari or []
    
    # Rapordaki kodlardan herhangi biri, beklenen kodlardan biriyle başlıyor mu? (Ör: E11.9, E11 ile başlar)
    eslesenler = [t for t in rapordaki_kodlar if any(t.upper().startswith(b) for b in beklenen_kodlar)]
    
    if eslesenler:
        # Geçerli kod bulundu, sorun yok.
        return []
    else:
        # Aranan kod raporda yok, HATA ver!
        return [Bulgu(
            kural_id=kural["id"],
            seviye=kural.get("seviye", "HATA"),
            baslik=kural["baslik"],
            mesaj=kural["mesaj_yok"].strip(),
            sut_madde=kural.get("sut_madde"),
            kanit=f"Tetikleyen Ürün: {etiket} | Aranan Kodlar: {', '.join(beklenen_kodlar)} | Rapordaki Kodlar: {', '.join(rapordaki_kodlar) if rapordaki_kodlar else 'Yok'}"
        )]


def _yasakli_ibare_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    """Tetikleyici ilaçlar varsa ve raporda yasaklı/çelişen bir ifade geçiyorsa hata verir."""
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(havuz, "urun")
    tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(tetikleyici, s)]
    
    if not tetikleyen:
        return []
        
    metin = rapor.serbest_metin.lower()
    yasakli_kaliplar = kural.get("yasakli_kaliplar", [])
    
    bulunanlar = [k for k in yasakli_kaliplar if k.lower() in metin]
    
    if bulunanlar:
        return [Bulgu(
            kural_id=kural["id"],
            seviye=kural.get("seviye", "HATA"),
            baslik=kural["baslik"],
            mesaj=kural["mesaj"],
            sut_madde=kural.get("sut_madde"),
            kanit=f"Tetikleyen: {', '.join(tetikleyen)} | Tespit Edilen Çelişki: '{bulunanlar[0]}'"
        )]
    return []


def _aranan_ibare_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    """Tetikleyici ilaç varsa, rapor metninde belirli kelimelerin geçip geçmediğini kontrol eder."""
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(havuz, "urun")
    tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(tetikleyici, s)]
    
    if not tetikleyen:
        return []
        
    metin = rapor.serbest_metin.lower()
    aranan_kaliplar = kural.get("aranan_kaliplar", [])
    
    # Rapor metninde bu kelimelerden herhangi biri var mı?
    bulunanlar = [k for k in aranan_kaliplar if k.lower() in metin]
    
    if bulunanlar:
        # Kelime bulundu -> YEŞİL IŞIK (BİLGİ)
        return [Bulgu(
            kural_id=kural["id"] + "_VAR",
            seviye="BILGI",
            baslik=kural.get("baslik_var", "Şartlar Sağlandı"),
            mesaj=kural.get("mesaj_var", f"Raporda gerekli ibare tespit edildi."),
            sut_madde=kural.get("sut_madde"),
            kanit=f"Bulunan İbare: '{bulunanlar[0].upper()}'"
        )]
    else:
        # Kelime bulunamadı -> SARI IŞIK (UYARI)
        return [Bulgu(
            kural_id=kural["id"] + "_YOK",
            seviye=kural.get("seviye", "UYARI"),
            baslik=kural.get("baslik_yok", "Eksik İbare"),
            mesaj=kural.get("mesaj_yok", "Gerekli ibare bulunamadı, manuel kontrol edin."),
            sut_madde=kural.get("sut_madde"),
            kanit=f"Tetikleyen Ürün: {', '.join(tetikleyen)}"
        )]
    

def _osteoporoz_kurali(kural: dict, rapor: Rapor, recete: Recete | None, havuz: list[Ilac]) -> list[Bulgu]:
    """Osteoporoz ilaçlarında Yaş, Kırık ve T-Skoru denetimi yapar."""
    tetikleyici = kural.get("tetikleyici", {})
    gruplar = _gruplar(havuz, "urun")
    tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(tetikleyici, s)]
    
    if not tetikleyen:
        return []
        
    metin = (rapor.serbest_metin or "").lower()
    yas = getattr(rapor, "hasta_yasi", 65) or 65
    t_skoru = getattr(rapor, "t_skoru", None)
    
    # 1. 75 YAŞ ÜZERİ İSTİSNASI
    if yas >= 75:
        return [Bulgu(kural_id=kural["id"]+"_YAS", seviye="BILGI", baslik="75 Yaş Üzeri (Skor Aranmaz)", mesaj=f"Hasta {yas} yaşında. 75 yaş ve üzeri hastalarda T-Skoru veya kırık şartı aranmaksızın ödenir.", sut_madde=kural.get("sut_madde"), kanit=f"Girilen Yaş: {yas}")]

    # 2. PATOLOJİK KIRIK İSTİSNASI (T-Skoru <= -1.0 yeterli)
    if "patolojik kırık" in metin or "patolojik kirik" in metin:
        if t_skoru is not None and t_skoru <= -1.0:
            return [Bulgu(kural_id=kural["id"]+"_KIRIK_OK", seviye="BILGI", baslik="Patolojik Kırık Mevcut", mesaj=f"Raporda kırık mevcut. T-Skoru ({t_skoru}) sınır olan -1.0 ve altında. Ödenir.", sut_madde=kural.get("sut_madde"), kanit=f"T-Skoru: {t_skoru}")]
        elif t_skoru is None:
            return [Bulgu(kural_id=kural["id"]+"_KIRIK_EKS", seviye="HATA", baslik="T-Skoru Eksik", mesaj="Kırığı olan hastalarda T-Skorunun en az -1.0 olması gerekir. Skoru giriniz.", sut_madde=kural.get("sut_madde"), kanit="")]
        else:
            return [Bulgu(kural_id=kural["id"]+"_KIRIK_HATA", seviye="HATA", baslik="Kırık Var Ama Skor Yetersiz!", mesaj=f"Patolojik kırığı olanlarda T-Skoru en fazla -1.0 olabilir. Girilen: {t_skoru}. Ödenmez!", sut_madde=kural.get("sut_madde"), kanit=f"T-Skoru: {t_skoru}")]

    # T-Skoru girilmemişse hata ver
    if t_skoru is None:
        return [Bulgu(kural_id=kural["id"]+"_EKS", seviye="HATA", baslik="DEXA T-Skoru Eksik", mesaj="Osteoporoz tespiti için DEXA T-Skorunu girmelisiniz.", sut_madde=kural.get("sut_madde"), kanit=f"Tetikleyen: {', '.join(tetikleyen)}")]

    # 3. 65 YAŞ VE ÜZERİ (Kırıksız)
    if yas >= 65:
        if t_skoru <= -2.5:
            return [Bulgu(kural_id=kural["id"]+"_65_OK", seviye="BILGI", baslik="65+ Yaş Uygun", mesaj=f"{yas} yaşındaki hastada T-Skoru ({t_skoru}) sınır olan -2.5 ve altında. Ödenir.", sut_madde=kural.get("sut_madde"), kanit=f"Yaş: {yas}, Skor: {t_skoru}")]
        else:
            return [Bulgu(kural_id=kural["id"]+"_65_HATA", seviye="HATA", baslik="Yetersiz T-Skoru! (Kesinti Sebebi)", mesaj=f"65 yaş ve üzeri hastalarda T-Skoru en az -2.5 olmalıdır. Girilen: {t_skoru}. Ödenmez!", sut_madde=kural.get("sut_madde"), kanit=f"Yaş: {yas}, Skor: {t_skoru}")]

    # 4. 65 YAŞ ALTI (Kırıksız)
    if yas < 65:
        if t_skoru <= -3.0:
            return [Bulgu(kural_id=kural["id"]+"_GENC_OK", seviye="BILGI", baslik="65 Yaş Altı Uygun", mesaj=f"{yas} yaşındaki hastada T-Skoru ({t_skoru}) sınır olan -3.0 ve altında. Ödenir.", sut_madde=kural.get("sut_madde"), kanit=f"Yaş: {yas}, Skor: {t_skoru}")]
        else:
            return [Bulgu(kural_id=kural["id"]+"_GENC_HATA", seviye="HATA", baslik="Yetersiz T-Skoru! (Kesinti Sebebi)", mesaj=f"65 yaş altı hastalarda T-Skoru en az -3.0 olmalıdır. Girilen: {t_skoru}. Ödenmez!", sut_madde=kural.get("sut_madde"), kanit=f"Yaş: {yas}, Skor: {t_skoru}")]

        
    
def calistir(rapor: Rapor, recete: Recete | None, ks: KuralSeti) -> Sonuc:
    """Kural setini verilen rapor ve reçete üzerinde çalıştırır."""
    havuz: list[Ilac] = list(rapor.ilaclar)
    if recete and ks.ayarlar.get("receteyi_de_degerlendir", True):
        havuz += list(recete.ilaclar)

    # Raporsuz reçetede rapor ibaresi aranmaz; ibare reçete açıklamasında aranır.
    rapor_yok = recete is not None and not recete.rapor_var

    bulgular: list[Bulgu] = []

    for kural in ks.kurallar:
        tip = kural.get("tip")

        if tip == "kapsam_kontrolu":
            bulgular += _kapsam_kurali(kural, rapor, recete)
            continue
        if tip == "tarih_kontrolu":
            bulgular += _tarih_kurali(kural, rapor, recete)
            continue
        if tip == "ayrik_urun_notu":
            bulgular += _ayrik_urun_kurali(kural, havuz)
            continue
        if tip == "raporsuz_recete_kontrolu":
            bulgular += _raporsuz_recete_kurali(kural, ks, recete)
            continue
        if tip == "tekil_sinif_kontrolu":
            bulgular += _tekil_sinif_kurali(kural, havuz)
            continue
        if tip == "cok_kaynakli_ibare_kontrolu":
            bulgular += _cok_kaynakli_ibare_kurali(kural, ks, rapor, recete, havuz)
            continue
        if tip == "aranan_ibare_kontrolu":
            bulgular += _aranan_ibare_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "raporsuz_yasakli_urun":
            bulgular += _raporsuz_yasakli_urun_kurali(kural, recete)
            continue
        if tip == "tani_kodu_ibare_kontrolu":
            bulgular += _tani_kodu_ibare_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "brans_kontrolu":
            bulgular += _brans_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "yasakli_ibare_kontrolu":
            bulgular += _yasakli_ibare_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "osteoporoz_kontrolu":
            bulgular += _osteoporoz_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "doz_siniri_kontrolu":
            bulgular += _doz_siniri_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "ldl_kontrolu":
            bulgular += _ldl_kurali(kural, rapor, recete, havuz)
            continue
        if tip == "tani_kodu_kontrolu":
            bulgular += _tani_kodu_kurali(kural, rapor, recete, havuz)
            continue
        if rapor_yok and tip == "ibare_kontrolu":
            continue

        gruplar = _gruplar(havuz, kural.get("kapsam", "urun"))
        tetikleyici = kural.get("tetikleyici", {})
        tetikleyen = [e for e, s in gruplar if _tetiklendi_mi(tetikleyici, s)]
        if not tetikleyen:
            continue

        etiket = ", ".join(tetikleyen)
        if tip == "ibare_kontrolu":
            bulgular.append(_ibare_kurali(kural, ks, rapor, etiket))
        elif tip in ("bilgi_notu", "birliktelik_uyarisi"):
            bulgular.append(
                Bulgu(
                    kural_id=kural["id"],
                    seviye=kural.get("seviye", "BILGI"),
                    baslik=kural["baslik"],
                    mesaj=kural["mesaj"].strip(),
                    sut_madde=kural.get("sut_madde"),
                    kanit=f"Tetikleyen ürün: {etiket}",
                )
            )

    sirali = {"HATA": 0, "UYARI": 1, "BILGI": 2}
    bulgular.sort(key=lambda b: sirali[b.seviye])
    return Sonuc(bulgular=bulgular, kural_seti_surumu=ks.surum)
