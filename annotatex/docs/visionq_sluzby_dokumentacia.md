# VisionQ — Dokumentácia detekčných služieb

> Verzia: apríl 2026  
> Jazyk: Slovak / Slovenčina

---

## Obsah

1. [Čo je detekčná služba?](#1-čo-je-detekčná-služba)
2. [Čo systém detekuje?](#2-čo-systém-detekuje)
3. [Vstupné režimy](#3-vstupné-režimy)
4. [Konfigurácia služby — prehľad všetkých polí](#4-konfigurácia-služby--prehľad-všetkých-polí)
5. [Výstup — JSON správa](#5-výstup--json-správa)
6. [Spúšťač brány (Gate Trigger)](#6-spúšťač-brány-gate-trigger)
7. [Režimy výstupu](#7-režimy-výstupu)
8. [Receiver Dashboard (webové rozhranie)](#8-receiver-dashboard-webové-rozhranie)
9. [Živý náhľad (Preview)](#9-živý-náhľad-preview)
10. [Nahrávanie streamu (Input Recording)](#10-nahrávanie-streamu-input-recording)
11. [Zber datasetov (Dataset Capture)](#11-zber-datasetov-dataset-capture)
12. [Debug log (CSV)](#12-debug-log-csv)
13. [Viacero služieb naraz](#13-viacero-služieb-naraz)
14. [Príklady nasadenia](#14-príklady-nasadenia)

---

## 1. Čo je detekčná služba?

VisionQ dokáže bežať ako **jedna alebo viacero detekčných služieb súčasne**. Každá služba:

- prijíma video vstup (kamera cez RTSP, HTTP volania, alebo lokálny video súbor),
- spúšťa YOLO model na každom snímku,
- určuje, čo sa nachádza v zábere a akým smerom sa objekt pohybuje,
- výsledok posiela ako **JSON správu** na nakonfigurovanú výstupnú adresu.

Každá služba má vlastné meno, vlastný model a vlastné nastavenia — môžu bežať navzájom nezávisle.

---

## 2. Čo systém detekuje?

Systém pracuje s **YOLO modelom**, ktorý rozpoznáva nasledujúce triedy objektov:

| Trieda | Popis |
|--------|-------|
| `car` | Auto — čelný alebo bočný pohľad |
| `car_rear` | Auto — pohľad zozadu (zadná časť vozidla) |

Pre každú detekovanú triedu systém určí:

### Detekcia prítomnosti
- **Detekované** (`detected: true`) — objekt je v zábere.
- **Nedetekované** (`detected: false`) — objekt sa v zábere nenachádza.

### Smer pohybu
Smer je určovaný na základe pohybu ťažiska bounding boxu a zmeny jeho plochy počas posledných snímkov (typicky 8 snímkov):

| Hodnota | Popis |
|---------|-------|
| `forward` | Auto sa pohybuje smerom ku kamere / dovnútra areálu |
| `backward` | Auto sa pohybuje od kamery / smerom von z areálu |
| `idle` | Auto stojí alebo sa pohybuje veľmi pomaly |
| `no_car` | Objekt nie je detekovaný |

> **Poznámka:** Systém nehlási `idle` ako prvý stav hneď po objavení auta — čaká na spoľahlivý pohybový signál, takže typický výstup vyzerá: `forward → idle → no_car`.

---

## 3. Vstupné režimy

Každá služba si vyberá **jeden** zo troch vstupných režimov.

### 3.1 RTSP — IP kamera

Systém sa priamo pripojí k IP kamere cez RTSP protokol.

**Povinné polia:**
| Pole | Príklad | Popis |
|------|---------|-------|
| Camera IP | `192.168.1.100` | IP adresa kamery v lokálnej sieti |
| RTSP port | `554` | Štandardný port pre RTSP (zvyčajne nemeniť) |
| Username | `admin` | Prihlasovacie meno kamery |
| Password | `heslo123` | Heslo kamery |
| Channel path | `Streaming/Channels/102` | Cesta k streamu (závisí od výrobcu kamery) |
| Frame interval | `0.25 s` | Ako často sa snímok spracuje (0.25 s = 4 snímky za sekundu) |

Systém zobrazí výsledné RTSP URL vo formáte:
```
rtsp://admin:heslo123@192.168.1.100:554/Streaming/Channels/102
```

---

### 3.2 HTTP — externé volania

Systém spustí lokálny HTTP server. Externá aplikácia mu posiela obrázky cez HTTP POST požiadavku.

**Endpoint:** `POST http://<host>:<port>/detect`  
**Formát:** `multipart/form-data`, pole `images` (3–5 obrázkov naraz odporúčané)

**Polia:**
| Pole | Príklad | Popis |
|------|---------|-------|
| Listen host | `0.0.0.0` | Na akej adrese počúva (0.0.0.0 = všetky rozhrania) |
| Listen port | `5050` | Port, na ktorom čaká na požiadavky |

Tento režim je vhodný, ak externý systém sám riadi zachytávanie snímkov a potrebuje len analýzu.

---

### 3.3 Video súbor — simulácia živého streamu

Služba číta lokálny video súbor rovnako, ako by to bol živý stream.

**Polia:**
| Pole | Príklad | Popis |
|------|---------|-------|
| Video file | `/video/zaznam.mp4` | Cesta k súboru (MP4, AVI, MOV, MKV) |
| Frame interval | `0.25 s` | Interval spracovania snímkov |
| Loop video | ✓ / ✗ | Či sa má video opakovať po skončení |

Tento režim je ideálny na **testovanie a ladenie** bez potreby fyzickej kamery.

---

## 4. Konfigurácia služby — prehľad všetkých polí

### Základné nastavenia

| Pole | Popis |
|------|-------|
| **Name** | Unikátny názov služby (napr. `brana_vstup`, `brana_vychod`). Objaví sa v JSON výstupe aj v Receiver dashboarde. |
| **Model** | Cesta k YOLO `.pt` súboru s natrénovanými váhami. |
| **Auto-start** | Ak zaškrtnuté, služba sa spustí automaticky pri otvorení VisionQ. |

### Výstup

| Pole | Príklad | Popis |
|------|---------|-------|
| Output host | `127.0.0.1` | IP adresa, na ktorú systém posiela JSON výsledky |
| Output port | `6060` | Port prijímača (Receiver beží na tomto porte) |

> Výsledky sa posielajú ako `POST /result` na `http://<output_host>:<output_port>/result`.

### Detekčné nastavenia

| Pole | Popis |
|------|-------|
| **Confidence threshold** | Minimálna istota detekcie (0.0–1.0). Detekcie s nižšou hodnotou sú ignorované. Odporúčaná hodnota: `0.5`. |
| **Strict output** | Odosiela výsledky iba keď je smer spoľahlivo určený (`forward`/`backward`) alebo keď auto zmizlo (`no_car`). Nevhodný pre systémy, ktoré potrebujú vedieť aj stav `idle`. |
| **State changes only** | Odosiela výsledky iba pri zmene stavu (napr. `forward → idle`, `idle → no_car`). Minimalizuje počet správ — každá zmena sa reportuje práve raz. |

---

## 5. Výstup — JSON správa

Každý výsledok detekcie je odoslaný ako HTTP POST s JSON telom na nakonfigurovanú výstupnú adresu.

### Štruktúra JSON

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

### Popis polí

| Pole | Typ | Popis |
|------|-----|-------|
| `service_name` | string | Meno služby, ktorá správu vygenerovala |
| `car.detected` | bool | Či je auto (trieda `car`) viditeľné v snímku |
| `car.direction` | string | Smer pohybu: `forward`, `backward`, `idle`, `no_car` |
| `car.confidence` | float (0–1) | Istota detekcie (napr. `0.96` = 96 %) |
| `car_rear.detected` | bool | Či je viditeľná zadná časť auta (trieda `car_rear`) |
| `car_rear.direction` | string | Smer pohybu zadnej časti |
| `car_rear.confidence` | float (0–1) | Istota detekcie zadnej časti |
| `gate.open` | bool | `true` ak systém vyhodnotil, že brána má byť otvorená |
| `frames_analyzed` | int | Počet snímkov použitých na určenie smeru |

### Typická sekvencia správ (State changes only)

```
1. { "car": {"detected": true,  "direction": "forward", ...}, "gate": {"open": false} }
2. { "car": {"detected": true,  "direction": "idle",    ...}, "gate": {"open": true}  }
3. { "car": {"detected": false, "direction": "no_car",  ...}, "gate": {"open": false} }
```

---

## 6. Spúšťač brány (Gate Trigger)

Systém dokáže automaticky signalizovať, že **brána má byť otvorená**, keď auto stojí v bezprostrednej blízkosti kamery.

### Ako to funguje

1. Systém sleduje **plochu bounding boxu** (ohraničujúceho obdĺžnika) detekovaného auta.
2. Keď auto stojí (`idle`) a jeho bounding box je väčší alebo rovnaký ako nastavená **minimálna plocha**, nastaví `gate.open = true`.
3. Toto sa reportuje **raz** pri prechode z `false` na `true`.
4. Keď auto odíde, `gate.open` sa resetuje.

### Konfigurácia

| Pole | Príklad | Popis |
|------|---------|-------|
| Min bbox area | `400000` | Minimálna plocha bounding boxu v pixeloch² (0 = funkcia vypnutá) |

### Ako zistiť správnu hodnotu prahu

1. Spustite službu a zapnite **Debug log** (tlačidlo `⏺ Debug` v hlavnom okne).
2. Postavte auto pred kameru na pozíciu, kde má byť brána otvorená.
3. V CSV súbore nájdite stĺpec `area` pre triedu `car` — táto hodnota je váš prah.
4. Nastavte hodnotu mierne nižšie (napr. 80 % nameranej hodnoty), aby systém spoľahlivo reagoval.

---

## 7. Režimy výstupu

| Režim | Popis | Kedy použiť |
|-------|-------|-------------|
| **Kontinuálny** (predvolený) | Výsledok sa odosiela po každom spracovanom snímku | Keď externý systém potrebuje neustály tok dát |
| **Strict output** | Odosiela len keď je smer jasný alebo auto zmizlo | Keď nechcete spracovávať `idle` správy |
| **State changes only** | Odosiela len raz pri každej zmene stavu | **Odporúčané pre väčšinu nasadení** — minimálny šum, jednoznačné udalosti |

---

## 8. Receiver Dashboard (webové rozhranie)

VisionQ obsahuje vstavaný web server (Receiver), ktorý prijíma a zobrazuje výsledky zo všetkých aktívnych služieb.

**Prístup:** `http://127.0.0.1:6060` v prehliadači

### Čo vidíte v dashboarde

- Každá služba má vlastný **panel** s názvom a štatistikami.
- Štatistiky: celkový počet správ, počet detekcií auta, počet detekcií zadnej časti, posledný smer.
- Tabuľka posledných výsledkov:

| Stĺpec | Popis |
|--------|-------|
| TIME | Čas prijatia výsledku |
| GATE | `▲ OPEN` ak bola brána otvorená, inak prázdne |
| CAR | Či bolo auto detekované |
| CAR DIR | Smer pohybu auta + istota |
| REAR | Či bola detekovaná zadná časť |
| REAR DIR | Smer pohybu zadnej časti + istota |

- Riadky so zeleným pozadím označujú momenty, keď bola brána otvorená.
- Dashboard sa **automaticky obnovuje** každých 0,8 sekundy.

---

## 9. Živý náhľad (Preview)

Pre každú bežiacu službu je dostupný **živý náhľad** — okno zobrazujúce aktuálne spracovávané snímky vrátane vizualizácie detekcií (bounding boxy, trieda, istota).

### Ovládanie prehrávania (Video / RTSP režim)

| Prvok | Funkcia |
|-------|---------|
| ⏮ | Skok na začiatok |
| -15s / -5s | Skok dozadu o 15 / 5 sekúnd |
| ▶ / ⏸ | Prehrávanie / Pauza |
| +5s / +15s | Skok dopredu o 5 / 15 sekúnd |
| Rýchlosť (×0.5 – ×4) | Zmena rýchlosti prehrávania |
| Posúvač (seek bar) | Kliknutím skočíte na ľubovoľné miesto vo videu |

> **Tip:** Pri podržaní myši nad posúvačom sa zobrazí čas v minútach a sekundách (napr. `12:34`), čo pomáha pri navigácii v dlhých záznamoch.

### Snímkový krok (Frame step)

Tlačidlá `◀ Frame` a `Frame ▶` posunú video o jeden snímok dozadu / dopredu (len pri pauze). Užitočné pri podrobnej analýze.

### Tlačidlo ⏺ Rec

Spustí/zastaví nahrávanie aktuálneho live streamu / videa do MP4 súboru. Súbor sa uloží do nakonfigurovaného adresára (predvolene `~/VisionQ_recordings/`).

### Tlačidlo ⏺ Debug

Spustí/zastaví zápis podrobného CSV logu každého snímku (pozri sekciu 12).

---

## 10. Nahrávanie streamu (Input Recording)

Každá RTSP alebo video služba môže **automaticky nahrávať** vstupný stream do lokálneho MP4 súboru.

| Pole | Popis |
|------|-------|
| Auto-start recording | Nahrávanie sa spustí automaticky so spustením služby |
| Output folder | Priečinok, kam sa ukladajú súbory (predvolene `~/VisionQ_recordings/`) |

Súbory sú pomenované podľa vzoru:
```
<meno_sluzby>_<dátum_čas>.mp4
```
Príklad: `brana_vstup_20260422_094512.mp4`

FPS nahrávky sa určuje automaticky z nastaveného intervalu snímkov.

---

## 11. Zber datasetov (Dataset Capture)

Systém môže súbežne s detekciou **ukladať surové snímky** (bez anotácií) pre neskoršie použitie na tréning modelu.

| Pole | Popis |
|------|-------|
| Save raw frames | Zapnutie zberu datasetov |
| Capture every N frames | Snímok sa uloží každých N spracovaných snímkov (napr. každý 10.) |
| Output folder | Priečinok pre uloženie snímkov |

Štruktúra priečinkov:
```
<output_folder>/
  <meno_sluzby>/
    20260422_094512_123.jpg
    20260422_094522_456.jpg
    ...
```

Každý súbor je pomenovaný časovou pečiatkou — snímky sú chronologicky zoradené a kolízie sú vylúčené.

---

## 12. Debug log (CSV)

Pre ladenie detekcie smeru a nastavovania prahu brány je k dispozícii **detailný CSV log** každého snímku.

### Ako zapnúť

V hlavnom okne VisionQ kliknite na **`⏺ Debug`** vedľa príslušnej služby. Zobrazí sa cesta k súboru CSV. Kliknutím znova log vypnete a súbor sa uzavrie.

Súbory sa ukladajú do `~/VisionQ_debug/` s názvom:
```
direction_<meno_sluzby>_<dátum_čas>.csv
```

### Stĺpce CSV

| Stĺpec | Popis |
|--------|-------|
| `timestamp` | Čas snímku (HH:MM:SS.mmm) |
| `service` | Meno služby |
| `cls` | Trieda objektu (`car` alebo `car_rear`) |
| `detected` | Či bol objekt detekovaný |
| `cx`, `cy` | Súradnice ťažiska bounding boxu (pixely) |
| `area` | Plocha bounding boxu (pixely²) |
| `conf` | Istota detekcie (0–1) |
| `buf_len` | Počet snímkov v aktuálnom pohybovom bufferi |
| `cx_rel`, `cy_rel`, `area_rel` | Relatívna rýchlosť zmeny signálov (% per snímok) |
| `cx_vote`, `cy_vote`, `area_vote` | Hlas každého signálu (1 = dopredu, -1 = dozadu, 0 = neutrálny) |
| `score` | Celkové skóre (súčet hlasov) |
| `raw_dir` | Smer pred aplikovaním hysterézy |
| `final_dir` | Výsledný smer po hysteréze |
| `gate_threshold` | Nakonfigurovaný prah brány |
| `gate_open` | Či je v tomto snímku brána otvorená |

---

## 13. Viacero služieb naraz

VisionQ umožňuje bežať **neobmedzený počet služieb súčasne** — každá so svojou kamerou, modelom a nastaveniami.

Príklady použitia:
- `brana_vstup` — kamera sledujúca príjazd (čelný pohľad)
- `brana_vychod` — kamera sledujúca odchod (čelný pohľad)
- `dvor` — kamera na dvore (sledovanie pohybu)

Každá služba:
- má vlastný port (ak ide o HTTP režim),
- odosiela výsledky na rovnakú alebo rôznu výstupnú adresu,
- objavuje sa ako samostatný panel v Receiver dashboarde,
- sa dá spustiť, zastaviť, editovať alebo duplikovať nezávisle.

---

## 14. Príklady nasadenia

### Príklad 1: Jedna vstupná brána, RTSP kamera, integrácia s externým systémom

```
[IP Kamera] 
    ↓ RTSP stream
[VisionQ — služba "brana_vstup"]
    ↓ HTTP POST JSON
[Externá aplikácia na porte 6060]
```

**Konfigurácia:**
- Vstup: RTSP, IP kamery, interval 0.25 s
- State changes only: ✓ (každá udalosť príde práve raz)
- Gate Trigger: nastavený prah podľa reálnej plochy auta pred bránou
- Výstup: `127.0.0.1:6060` (alebo IP externého servera)

**Typický tok správ:**
```json
{"service_name": "brana_vstup", "car": {"detected": true, "direction": "forward", "confidence": 0.96}, "gate": {"open": false}}
{"service_name": "brana_vstup", "car": {"detected": true, "direction": "idle",    "confidence": 0.98}, "gate": {"open": true}}
{"service_name": "brana_vstup", "car": {"detected": false,"direction": "no_car",  "confidence": 0.0},  "gate": {"open": false}}
```

---

### Príklad 2: Testovanie na video súbore

- Vstup: Video súbor (lokálny MP4 záznam)
- Loop: ✓
- Debug log: ✓ (zapnúť pred testom, vypnúť po)
- State changes only: ✓

Postup:
1. Pridajte novú službu, zvoľte "Use local video file".
2. Vyberte video súbor.
3. Spustite službu — v náhľade uvidíte spracovávané snímky.
4. Zapnite Debug log a sledujte CSV v reálnom čase.
5. Otvorte Receiver dashboard (`http://127.0.0.1:6060`) pre prehľad výsledkov.

---

### Príklad 3: Integrácia s externou aplikáciou

Externá aplikácia počúva na `POST /result` (alebo ľubovoľnom vlastnom endpointe).

**Minimálny Python prijímač:**
```python
from flask import Flask, request
app = Flask(__name__)

@app.route("/result", methods=["POST"])
def receive():
    data = request.get_json()
    service = data.get("service_name")
    gate    = data.get("gate", {}).get("open", False)
    car_dir = data.get("car", {}).get("direction", "no_car")
    
    print(f"[{service}] smer={car_dir}, brana={'OPEN' if gate else 'closed'}")
    
    if gate:
        # tu spustite otváranie brány
        pass
    
    return {"ok": True}

app.run(host="0.0.0.0", port=6060)
```

---

*Dokument vygenerovaný pre internú potrebu projektu VillaPro / VisionQ.*
