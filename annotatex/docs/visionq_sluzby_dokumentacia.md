# VisionQ — Dokumentácia detekčných služieb

> Apríl 2026

---

## Obsah

1. [Čo systém detekuje](#1-čo-systém-detekuje)
2. [Pridanie novej služby](#2-pridanie-novej-služby)
3. [Bežiaca služba — nahrávanie, debug, náhľad](#3-bežiaca-služba--nahrávanie-debug-náhľad)
4. [Receiver Dashboard](#4-receiver-dashboard)

---

## 1. Čo systém detekuje

Každá služba beží s vlastným YOLO modelom, ktorý rozpoznáva dve triedy objektov:

| Trieda | Popis |
|--------|-------|
| `car` | Auto — čelný alebo bočný pohľad |
| `car_rear` | Auto — pohľad zozadu |

Pre každú triedu systém určuje **smer pohybu** na základe pohybu ťažiska bounding boxu a zmeny jeho veľkosti počas posledných snímkov:

| Smer | Popis |
|------|-------|
| `forward` | Auto sa pohybuje smerom ku kamere / dovnútra areálu |
| `backward` | Auto sa pohybuje od kamery / smerom von |
| `idle` | Auto stojí alebo sa pohybuje príliš pomaly |
| `no_car` | Objekt nie je v zábere |

Systém nereportuje `idle` ako prvý stav hneď po objavení auta — čaká na spoľahlivý pohybový signál. Typická sekvencia výsledkov vyzerá takto:

```
forward → idle → no_car
```

---

## 2. Pridanie novej služby

Každá služba má vlastné meno, vlastný model a vlastné nastavenia. Viacero služieb môže bežať súčasne — napríklad jedna pre vstupnú bránu, druhá pre výstupnú.

Nová služba sa pridáva cez tlačidlo **Add Service**, ktoré otvorí konfiguračný formulár rozdelený do niekoľkých sekcií.

---

### Základné nastavenia

| Pole | Popis |
|------|-------|
| **Name** | Unikátny názov služby (napr. `brana_vstup`). Objaví sa v JSON výstupe aj v Receiver dashboarde. Názov sa po uložení nedá zmeniť — na zmenu použite Duplicate. |
| **Model** | Cesta k `.pt` súboru s natrénovanými váhami YOLO modelu. |
| **Auto-start** | Ak zaškrtnuté, služba sa spustí automaticky pri každom otvorení VisionQ. |

---

### Input Source — zdroj vstupu

Každá služba si vyberá jeden z troch vstupných režimov.

#### RTSP — IP kamera

Systém sa priamo pripojí k IP kamere cez RTSP protokol a sám sťahuje snímky.

| Pole | Príklad | Popis |
|------|---------|-------|
| Camera IP | `192.168.1.100` | IP adresa kamery v lokálnej sieti |
| RTSP port | `554` | Štandardný RTSP port (zvyčajne nemeniť) |
| Username | `admin` | Prihlasovacie meno kamery |
| Password | `heslo123` | Heslo kamery |
| Channel path | `Streaming/Channels/102` | Cesta k streamu — závisí od výrobcu kamery |
| Frame interval | `0.25 s` | Ako často sa snímok spracuje. `0.25 s` = 4 snímky za sekundu. Nižšia hodnota = väčšia záťaž procesora. |

Systém zobrazí výsledné RTSP URL priamo v dialógu, napr.:
```
rtsp://admin:heslo123@192.168.1.100:554/Streaming/Channels/102
```

---

#### HTTP — externé volania

Systém spustí lokálny HTTP server a čaká, kým mu externá aplikácia pošle obrázky.

| Pole | Príklad | Popis |
|------|---------|-------|
| Listen host | `0.0.0.0` | Na akej adrese počúva. `0.0.0.0` znamená všetky sieťové rozhrania. |
| Listen port | `5050` | Port, na ktorom čaká na požiadavky. Každá HTTP služba musí mať iný port. |

Externá aplikácia posiela snímky na:
```
POST http://<host>:<port>/detect
```
Formát: `multipart/form-data`, pole `images` (odporúčané 3–5 obrázkov naraz).

---

#### Video súbor — simulácia živého streamu

Služba číta lokálny video súbor rovnako, ako by bol živý stream. Používa sa na testovanie a ladenie bez fyzickej kamery.

| Pole | Príklad | Popis |
|------|---------|-------|
| Video file | `zaznam.mp4` | Cesta k súboru (MP4, AVI, MOV, MKV) |
| Frame interval | `0.25 s` | Interval spracovania snímkov — rovnaký význam ako pri RTSP |
| Loop video | ✓ / ✗ | Či sa má video opakovať po skončení |

---

### Result Output — kam sa posielajú výsledky

Každý výsledok detekcie sa odošle ako JSON správa cez HTTP POST na nakonfigurovanú adresu.

| Pole | Príklad | Popis |
|------|---------|-------|
| Output host | `127.0.0.1` | IP adresa prijímača výsledkov |
| Output port | `6060` | Port prijímača. Predvolene tu beží Receiver Dashboard. |

**Štruktúra JSON výstupu:**

```json
{
  "service_name": "brana_vstup",
  "car": {
    "detected": true,
    "direction": "forward",
    "confidence": 0.96
  },
  "car_rear": {
    "detected": false,
    "direction": "no_car",
    "confidence": 0.0
  },
  "gate": {
    "open": false
  },
  "frames_analyzed": 1
}
```

| Pole | Typ | Popis |
|------|-----|-------|
| `service_name` | string | Meno služby |
| `car.detected` | bool | Či je auto viditeľné v snímku |
| `car.direction` | string | `forward`, `backward`, `idle`, alebo `no_car` |
| `car.confidence` | float 0–1 | Istota detekcie (napr. `0.96` = 96 %) |
| `car_rear.detected` | bool | Či je viditeľná zadná časť auta |
| `car_rear.direction` | string | Smer pohybu zadnej časti |
| `car_rear.confidence` | float 0–1 | Istota detekcie zadnej časti |
| `gate.open` | bool | `true` keď systém vyhodnotí, že brána má byť otvorená |
| `frames_analyzed` | int | Počet snímkov použitých na analýzu |

---

### Detection Settings — nastavenia detekcie

| Pole | Popis | Kedy použiť |
|------|-------|-------------|
| **Confidence threshold** | Minimálna istota detekcie (0–1). Detekcie s nižšou hodnotou sú ignorované. | Odporúčaná hodnota: `0.5`. Zvýšte ak dostávate príliš veľa falošných detekcií. |
| **Strict output** | Odosiela výsledky len keď je smer spoľahlivo určený, alebo keď auto zmizlo (`no_car`). Ignoruje fázu budovania bufferu. | Pre systémy, ktoré nepotrebujú vedieť o stave `idle`. |
| **State changes only** | Odosiela výsledok len raz pri každej zmene stavu (`forward → idle`, `idle → no_car`...). | **Odporúčané pre väčšinu nasadení.** Minimalizuje počet správ — každá udalosť príde práve raz. |

---

### Dataset Capture — zber trénovacích dát

Systém môže súbežne s detekciou ukladať surové snímky pre neskorší tréning modelu.

| Pole | Popis |
|------|-------|
| Save raw frames | Zapnutie zberu |
| Capture every N frames | Snímok sa uloží každých N spracovaných snímkov (napr. každý 10.) |
| Output folder | Priečinok pre uloženie — ak prázdne, použije sa predvolený adresár |

Snímky sa ukladajú do podpriečinka podľa mena služby, pomenované časovou pečiatkou:
```
<output_folder>/<meno_sluzby>/20260422_094512_123.jpg
```

---

### Input Recording — nahrávanie vstupu

Dostupné len pre RTSP a video režim. Systém môže automaticky nahrávať vstupný stream do MP4 súboru.

| Pole | Popis |
|------|-------|
| Auto-start recording | Nahrávanie sa spustí automaticky so spustením služby |
| Output folder | Priečinok pre MP4 súbory (predvolene `~/VisionQ_recordings/`) |

Súbory sú pomenované:
```
<meno_sluzby>_<dátum_čas>.mp4
```

---

### Gate Trigger — spúšťač brány

Systém dokáže automaticky signalizovať, že brána má byť otvorená, keď auto stojí priamo pred kamerou.

**Ako to funguje:** Systém sleduje plochu bounding boxu detekovaného auta. Keď auto stojí (`idle`) a jeho bounding box je väčší alebo rovnaký ako nastavená minimálna plocha, nastaví `gate.open = true`. Táto udalosť sa reportuje práve raz — pri prechode zo zatvoreného stavu na otvorený.

| Pole | Popis |
|------|-------|
| Min bbox area | Minimálna plocha bounding boxu v pixeloch² (0 = funkcia vypnutá) |

**Ako zistiť správnu hodnotu:**
1. Zapnite Debug log (tlačidlo `⏺ Debug`).
2. Postavte auto pred kameru na pozíciu, kde má byť brána otvorená.
3. V CSV súbore nájdite stĺpec `area` pre triedu `car`.
4. Nastavte hodnotu mierne nižšie ako nameraná hodnota (cca 80 %) pre spoľahlivé spúšťanie.

---

## 3. Bežiaca služba — nahrávanie, debug, náhľad

Po spustení služby sú dostupné ďalšie ovládacie prvky priamo v hlavnom okne VisionQ.

### Nahrávanie (Rec)

Tlačidlo **⏺ Rec** spustí alebo zastaví nahrávanie vstupu do MP4 súboru za behu — bez nutnosti reštartovať službu. Funguje rovnako ako automatické nahrávanie, len sa ovláda manuálne.

---

### Debug log

Tlačidlo **⏺ Debug** spustí zápis podrobného CSV logu každého spracovaného snímku. Súbor sa uloží do `~/VisionQ_debug/`. Kliknutím znova log zastavíte a súbor sa uzavrie.

Tento log je primárne určený na **ladenie smeru pohybu a nastavenie prahu brány**. Obsahuje pre každý snímok:

| Stĺpec | Popis |
|--------|-------|
| `timestamp` | Čas snímku |
| `cls` | Trieda (`car` / `car_rear`) |
| `cx`, `cy` | Súradnice ťažiska bounding boxu |
| `area` | Plocha bounding boxu — kľúčová hodnota pre Gate Trigger |
| `conf` | Istota detekcie |
| `cx_vote`, `cy_vote`, `area_vote` | Hlas každého pohybového signálu |
| `score` | Celkové skóre smeru |
| `final_dir` | Výsledný smer po všetkých korekcií |
| `gate_open` | Či bola v tomto snímku brána otvorená |

---

### Živý náhľad (Preview)

Tlačidlo **Preview** otvorí okno so živým obrazom z kamery alebo videa. V náhľade sú vykresľované **YOLO detekcie** — bounding boxy s triedou a istotou pre každý detekovaný objekt.

#### Sledovanie streamu (RTSP režim)

V RTSP režime náhľad zobrazuje živý obraz z kamery. Nie je možné video posúvať ani pozastaviť — obraz plynie v reálnom čase.

#### Ovládanie prehrávania (Video režim)

Keď je zdrojom video súbor, v spodnej časti náhľadu sa zobrazí lišta s ovládacími prvkami:

| Prvok | Funkcia |
|-------|---------|
| ⏮ | Skok na začiatok |
| -15s / -5s | Skok dozadu o 15 / 5 sekúnd |
| ▶ / ⏸ | Prehrávanie / Pauza |
| +5s / +15s | Skok dopredu o 5 / 15 sekúnd |
| ◀ Frame / Frame ▶ | Posun o jeden snímok (len pri pauze) — vhodné na presnú analýzu |
| Rýchlosť (×0.5 – ×4) | Zmena rýchlosti prehrávania |
| Posúvač (seek bar) | Kliknutím skočíte na ľubovoľné miesto. Pri podržaní myši sa zobrazí čas v minútach (napr. `12:34`). |
| Čítač | Zobrazuje aktuálnu pozíciu a celkovú dĺžku videa vo formáte `MM:SS / MM:SS` |

---

## 4. Receiver Dashboard

VisionQ obsahuje vstavaný webový server, ktorý prijíma výsledky zo všetkých aktívnych služieb a zobrazuje ich v prehľadnom dashboarde.

**Prístup:** `http://127.0.0.1:6060` v prehliadači

Dashboard sa automaticky obnovuje každých 0,8 sekundy a nevyžaduje žiadne manuálne obnovenie stránky.

---

### Rozloženie

Každá aktívna služba má vlastný panel. Panely sa vytvárajú automaticky pri prvom prijatí výsledku od danej služby.

**Hlavička panelu** zobrazuje:
- Názov služby
- Stav (`Live · HH:MM:SS` — čas posledného výsledku)

**Štatistiky panelu:**

| Štatistika | Popis |
|------------|-------|
| Reports | Celkový počet prijatých správ od tejto služby |
| Car | Počet správ, kde bolo detekované auto (`car`) |
| Car rear | Počet správ, kde bola detekovaná zadná časť auta |
| Last dir | Posledný zaznamenaný smer |

---

### Tabuľka výsledkov

Každý prijatý výsledok sa zobrazí ako riadok v tabuľke (najnovší hore):

| Stĺpec | Popis |
|--------|-------|
| TIME | Čas prijatia výsledku |
| GATE | `▲ OPEN` ak bola pri tomto výsledku brána otvorená, inak prázdne |
| CAR | Prítomnosť auta (`● CAR` alebo `○ —`) |
| CAR DIR | Smer pohybu auta a istota detekcie (napr. `forward 96%`) |
| REAR | Prítomnosť zadnej časti (`● REAR` alebo `○ —`) |
| REAR DIR | Smer pohybu zadnej časti |

Riadky, kde bola brána otvorená (`gate.open = true`), sú zvýraznené zeleným pozadím.

---

### Farebné kódovanie smerov

| Farba | Smer |
|-------|------|
| Zelená | `forward` — auto prichádza |
| Oranžová | `backward` — auto odchádza |
| Žltá | `idle` — auto stojí |
| Sivá | Nie je detekované |
