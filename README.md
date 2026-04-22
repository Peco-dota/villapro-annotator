# aplikacia - requirements
## spustenie a konfiguracia

- Aplikacia sa spusta v terminali - nevytvara ziadne UI prvky ani grafiku (headless), bezi kym nedostane sig-term (CTRL+C)
- Bude mat konfiguracny subor - napriklad json. konfiguracny subor sa bude specifikovat cez argument -c alebo --config s cestou k suboru (default moze byt napriklad `~/.config/nejaky_nazov.json`)
- V konfiguracnom subore bude minimalne IP a port na ktorom bude pocuvat HTTP server. moznost pridat certifikaty pre HTTPS by bolo plus ale nieje podmienka, ale vacsina HTTPS serverov to uz podporuju, len im dat tie certifikaty.
- Dalsie nastavenia aplikacie mozu byt v tom subore - teda aplikacia si moze ukladat nastavenia do toho suboru.
- V pripade ak by bolo potrebne viac nastaveni a konfiguracny subor by nestacil a je potrebne vyuzit databazu - v tom pripade odporucam pouzivat postgresql (v nasej firme je to standard)
- Nastavovanie aplikacie by malo ist cez HTTP API endpointy (treba riesit aj nejaku autentifikaciu, napriklad API tokeny alebo aj uzivatelia)
- Konfiguracna webova aplikacia - predpokladam jednoducha staticka stranka s logikou v javascripte

## konektor do nasich aplikacii

1. HTTP API - idealne SSE (Server Sent Event) aby sme nemuseli robit polling (samozrejme podmieneny API tokenom) - toto by vyuzila by najma webova aplikacia ktoru pouzivate
2. Kazdy stream (kedze podporuje viacero kamier) by mal mat moznost zapnut TCP/SSL (TLS/mTLS) server - tam sa nakonfiguruje port
  - na nejakom porte - nasa aplikacia sa pripoji na ten TCP stream
  - nasa aplikacia spravidla nemusi posielat nic (nenapada ma co by mohla posielat, nechame otvorene do buducna)
  - vasa aplikacia len posielala json informacie vzdy ked sa nieco zmeni (mala by poslat z casu nacas aj informaciu ze sa nic nedeje - ako keepalive)
  - staci posielat json v jednom riadku a ako oddelovac pouzivat novy riadok '\n' - jedna sprava - jeden riadok
  - na ten TCP/SSL port sa moze pripojit N klientov a v tedy kazdemu klientovi treba poslat informaciu o zmene

## priklad aplikacie na inspiraciu - podobnu vec som riesil v tejto aplikacii

https://github.com/cortexm/ser2tcp
- je to velmi jednoduchy prevodnik medzi seriovymi portmi a TCP/SSL/WebSocket (vzdialeny pristup k seriovym portom pocitaca)
- vyuzivajucej HTTP API (tu pouzivam sice vlastny HTTP server - ale mozte pouzit cokolvek co je vam lepsie)
- kompletnu konfiguraciu cez web
- jeden konfiguracny subor .json kde sa uklada vsetko nastavenie aj uzivatelia ci API tokeny