# Ziqna uchun narx feedi talablari (do'konlar uchun)

Ziqna do'konlardan narxlarni **feed (XML fayl)** orqali oladi. Bu ko'pchilik do'konlar Yandex Market uchun
allaqachon yuritadigan **YML** formati. Agar sizda shunday fayl bo'lsa, havolasini yuborishingiz kifoya.

## Minimal talablar
| Maydon | Izoh |
|---|---|
| `<name>` | Tovar to'liq nomi (brend + model + xotira/hajm kabi muhim tavsif) |
| `<price>` | Joriy narx **so'mda**, faqat raqam (masalan `4300000`) |
| `<url>` | Tovarning sizning saytingizdagi sahifasi (http/https) |
| `available` | `offer` atributi: `true` (sotuvda bor) yoki `false` |

## Tavsiya etiladi (moslash aniqligini ancha oshiradi)
| Maydon | Nima uchun |
|---|---|
| `<barcode>` | Shtrix-kod (EAN/GTIN). Turli do'konlarning bir xil tovarini 100% aniq birlashtiradi |
| `<vendor>` va `<vendorCode>` | Brend va ishlab chiqaruvchi model kodi (masalan `RB37J5000SA`) |
| `<picture>` | Rasm havolasi |
| `<categoryId>` + `<categories>` | Kategoriyalar daraxti |
| `<currencyId>UZS</currencyId>` | Valyuta: faqat so'm qabul qilinadi |

## Misol
```xml
<?xml version="1.0" encoding="UTF-8"?>
<yml_catalog>
  <shop>
    <categories>
      <category id="1">Maishiy texnika</category>
      <category id="2" parentId="1">Muzlatgichlar</category>
    </categories>
    <offers>
      <offer id="1001" available="true">
        <url>https://dokon.uz/p/1001</url>
        <price>7900000</price>
        <currencyId>UZS</currencyId>
        <categoryId>2</categoryId>
        <picture>https://dokon.uz/img/1001.jpg</picture>
        <vendor>Samsung</vendor>
        <vendorCode>RB37J5000SA</vendorCode>
        <barcode>4006381333931</barcode>
        <name>Samsung RB37J5000SA muzlatgich 367 l</name>
      </offer>
    </offers>
  </shop>
</yml_catalog>
```

## Texnik qoidalar
- Fayl UTF-8, hajmi 150 MB gacha. Havola doimiy ishlashi kerak (ixtiyoriy: login/parol o'rniga yopiq havola).
- Yangilash: kuniga kamida 1-2 marta. Sotuvda yo'q tovarlarni `available="false"` qiling yoki feeddan olib tashlang.
- Narx sahifadagi narx bilan bir xil bo'lishi shart. Foydalanuvchi bosganda boshqa narx ko'rsa, ishonch yo'qoladi.
- Rangli variantlar bo'lsa, har birini alohida `offer` qilib bering (bizda eng arzon sotuvdagisi ko'rsatiladi).
- Aksessuarlar (g'ilof, kabel, filtr) feedda bo'lishi mumkin, ularni biz avtomatik ajratamiz.

## Tekshirish
Feed tayyor bo'lgach, quyidagi buyruq hisobot beradi (xatolar va tavsiyalar bilan):

```
python validate_feed.py https://dokon.uz/feed.xml
```
