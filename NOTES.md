# Maas Learning | Masterplan für Sourcera

## Auftrag und Ziel

Sourcera nennt den Track „The Liquid Briefing“. Aus einem Tag echter Finanznachrichten entsteht ein persönlicher Audiobeitrag. Die Redaktion bereitet jede Meldung einmal auf und kann daraus verschiedene Ausgaben erzeugen. Bei jeder gesprochenen Tatsachenbehauptung soll der Hörer den Originalartikel beim passenden Transkriptsatz öffnen können.

**Demo-Idee:** Gleicher Nachrichtentag, zwei Briefings für unterschiedliche Bedürfnisse.

| Profil | Ausgabe |
|---|---|
| Markt-Trader (EN) | Rund 2 Minuten auf Englisch. ActionForex und Invezz: Währungen, Zentralbanken, Unternehmenszahlen, dicht mit Zahlen samt Zeitraum. |
| Privatanleger (DE) | Rund 60 bis 90 Sekunden auf Deutsch, einfach erklärt, breite Themen aus IBTimes UK und Invezz DE. Deutsch, weil Sourcera das Lesen in anderer Sprache selbst vorschlägt (IDEAS_AND_TIPS Nr. 1), 119 von 120 deutschen Invezz-Artikeln ein englisches Gegenstück haben und wir jede gesprochene Zahl selbst gegenhören können. Oberfläche, README und Pitch auf Englisch. (Vorschlag 20.11. 15:00, Team entscheidet; Alternative: zweites englisches Profil für Einsteiger.) |

Wählt die tatsächlichen Schwerpunkte nach Sichtung der Feeds. Zeigt mindestens eine Meldung, die nur in einem Profil vorkommt, und wenn möglich eine gemeinsame Meldung mit verschiedener Tiefe.

## Was die Jury laut Unterlagen bewertet

**Gewichtung laut BuilderBase (20.11. 14:52):** Trust and accuracy 25 %, Fit to the listener 20 %, Making sense of the news 20 %, Scalability and cost 15 %, Listening experience 10 %, Path to product 10 %.

- **Wildcard-Hörer:** die Jury gibt live einen neuen Hörer vor. Das Profil muss also eine Eingabe sein (Interessen, Sprache, Länge, Tiefe), das Briefing entsteht dann in ein bis zwei Minuten neu. Feste Profile allein reichen nicht.
- **Drei Aussagen** aus dem Audio werden gegen die Quelle geprüft: Zahlen richtig, nichts erfunden, **widersprechende Quellen markiert**, **keine Anlageberatung**.
- **Antwortschlüssel:** die Bündelung wird gegen eine Musterlösung geprüft, und **die wichtigsten Storys kommen zuerst**.
- **Kosten:** billige Schritte (Code, kleines Modell) wo es geht, großes Modell nur wo nötig, und das sagen.
- **Produkt:** wer zahlt (Verlag, Hörer oder Werbung) und **wie die synthetische Stimme offengelegt wird** (ein Satz am Anfang des Audios).

| Kriterium | Beweis in der Demo |
|---|---|
| Vertrauen und Genauigkeit | Eine gesprochene Zahl im Transkript anklicken und den Wert im Originalartikel zeigen. Jede Tatsachenbehauptung hat eine Quellen-ID. |
| Personalisierung | Beide Ausgaben aus demselben Datenstand erzeugen. Auswahl, Detailtiefe, Sprache und Länge sind klar verschieden. |
| Aufbereitung | Gleiche Ereignisse aus mehreren Meldungen zu einer Story bündeln. Zeigt ein konkretes Beispiel. |
| Skalierbarkeit und Kosten | Einmal pro Artikel aufbereiten und für beide Profile wiederverwenden. Vollmenge und 10-faches Volumen kalkulieren. |
| Hörerlebnis | Zwei kurze, natürliche Audiobeispiele. Zahlen, Währungen und Namen vor der Aufnahme anhören. |
| Weg zum Produkt | Eine Finanzredaktion zahlt beispielsweise für Audioausgaben zu ihren bestehenden Newslettern. Die Redaktion prüft die vorbereiteten Themen und Quellen und gibt die Ausgaben frei. |

**Abgabe am Samstag, 21.11., bis 10:30 Uhr Ortszeit.** In BuilderBase unter **Hand in** oder **My team → Open hand-in** Projektname, Code auf dem Stand der Demo und ein **3-Minuten-Pitchvideo** abgeben. Das genaue Eingabefeld für Code und Video sowie den Zugriff der Jury früh in BuilderBase prüfen. Für Sourcera im Video oder in den zugehörigen Folien auch Käufer, Redaktionsablauf und Kosten für 1× und 10× erklären. Ob BuilderBase zusätzlich eine Präsentationsdatei annimmt, direkt im Formular prüfen.

Der Arbeitsordner nennt für Samstag den zweiten Pflicht-Check-in **11:00–11:45 Uhr** in der **Sint Janskerk, Vrijthof**, und das Finale ab **15:00 Uhr**. Zeiten am Eventtag in BuilderBase abgleichen.

## Daten, Zugänge und Werkzeuge

1. **BuilderBase.** Mit der eingeladenen E-Mail anmelden. Falls noch offen, **Join → Sourcera → With a team**. Eine Person lädt die zwei anderen ein. Unter **My team** prüfen, ob alle drei bei **Maas Learning** stehen. Unter **Resources → Reveal** findet ihr den OpenAI-Zugang. Der allgemeine n8n-Link steht laut Anleitung in einer Datei unter **Resources**.
2. **[Newstex-Download](https://hackathon.sourcera.news/).** JSONL bedeutet ein Artikel als strukturierter Datensatz pro Zeile. Laut Deck gab es am 19.11. rund 1.740 Artikel von Zacks, Invezz (EN/DE/NL), IBTimes UK und ActionForex. Es gibt eine Datei pro Feed und Felder für Titel, Datum, Sprache, Autor, Volltext, Kategorien und Link. Zacks ist seit 28. Juli beprobt, die übrigen Feeds ab 13. November. Tatsächliche Zahl, Struktur, Zeitraum und funktionierende URLs nach dem Download prüfen. Der Download war bei der Recherche nicht erreichbar, das ist noch keine Aussage über euren Browserzugang.
3. **OpenAI.** Das Modell liest ausgewählte Artikel und schlägt kompakte Fakten mit Artikel-ID und einer kurzen internen Belegstelle vor. Der Code prüft das Ergebnis und baut daraus das Skript. Zuerst eine kleine Anfrage mit dem Hackathon-Schlüssel und einem dort verfügbaren günstigen Textmodell testen.
4. **ElevenLabs.** Schlüssel laut BuilderBase-Anleitung über Discord. In einer kleinen Probe Stimme und Modell auswählen, einen Satz mit Datum, Prozentwert und Währung schicken und die MP3 abhören. Der Server sendet den geprüften Sprechertext. [Text-to-Speech-Dokumentation](https://elevenlabs.io/docs/api-reference/text-to-speech/convert)
5. **n8n.** Nicht Teil des Kerns (entschieden 20.11. 15:00): kein Kriterium verlangt es, und das Event-n8n erreicht unseren Rechner nicht. Erst wenn die Demo komplett läuft, optional ein kleiner n8n-Workflow mit Zeitplan (jeden Morgen 6 Uhr) als Beleg für "Every morning". Sonst nur als Folie: so liefe es täglich in der Redaktion.
6. **GitHub.** Das gemeinsame Repository ist der Ort für Code und Versionsgeschichte. Erst klären, ob bereits ein privates Team-Repo existiert. Jedes Mitglied arbeitet in einem eigenen Branch, also einem separaten Bearbeitungszweig. Über einen Pull Request prüft ein anderes Mitglied die Änderung vor dem Zusammenführen in `main`. Vor dem Push synchronisieren. Codex pusht nach ausdrücklicher Ansage. [GitHub-Dokumentation](https://docs.github.com/en/pull-requests/reference/pull-requests)

Aus den PDFs geht keine Pflicht für einen bestimmten Anbieter, GitHub oder einen öffentlichen Deploy hervor. Bestätigt das bei Bedarf direkt im Hand-in-Formular. Gebaut wird in Python: eine kleine Streamlit-App (eine Python-Datei, läuft im Browser): Hörerprofil eingeben, Briefing erzeugen, Player und Transkript mit klickbarer Quelle je Aussage (entschieden 20.11. 15:00, statt Node-Server). Gebaut wird mit Claude Code; die 50 USD OpenAI-Guthaben gehen nur in die Pipeline selbst. Ein öffentliches Deployment, zusätzliche Konten und Ausgaben außerhalb der Event-Credits brauchen vorher die Zustimmung des Teamleads.

**Lizenz und Schlüssel.** Newstex ist nur für den Hackathon lizenziert. Artikeltext darf nicht erneut veröffentlicht werden. Klärt mit Sourcera, welche Ausschnitte an den Event-OpenAI-Zugang dürfen und welche Artefakte im Pitchvideo zulässig sind. Teilt in der Demo eigene Formulierungen und Quellenlinks. Ignoriert vor dem ersten Commit `.env`, `data/` und `output/` sowie lokale Ausgaben und Volltextkopien. Exportiert bei Bedarf den n8n-Workflow als JSON ohne Schlüssel, eingebettete Header oder gespeicherte Testdaten. Nach dem Event gemäß Lizenz den Datensatz löschen und Kopien in lokalen Ausgaben oder Workflows mitprüfen. [n8n-Export](https://docs.n8n.io/build/manage-workflows/export-and-import.md)

## Was wir bauen

1. **Einlesen.** Ein festes Demo-Datum mit echten Meldungen auswählen und die Zeilen der JSONL-Dateien lokal lesen. Felder vereinheitlichen. Jede Quelle bekommt eine stabile ID. Beiträge mit fehlender URL oder fehlendem Text überspringen. Für die erste Demo etwa 20–40 Artikel mit mindestens einem klar erkennbaren Doppelbericht verwenden.
2. **Bündeln.** Doppelte URLs entfernen. Sehr ähnliche Titel und Meldungen zum selben Unternehmen oder Ereignis am selben Tag als Kandidaten prüfen. Mehrere Quellenlinks pro Story behalten. Meldungen zu verschiedenen Ereignissen getrennt halten.
3. **Fakten prüfen.** Pro Story zwei bis drei Fakten erfassen. Pro Fakt Artikel-ID, Wert, Einheit, Bezugszeitraum und interne Belegstelle behalten. Prüfen, dass Artikel-ID und Belegstelle aus dem Eingabebestand stammen. Werte samt Einheit und Zeitraum im belegenden Satz prüfen. Widersprüche auslassen oder klar mit Quelle und Datum zuordnen. Hört und prüft jede gesprochene Aussage der Demo von Hand. Eine passende Zahl im Artikel allein belegt noch keine Aussage über ihren Zusammenhang.
4. **Briefings schreiben.** Aus demselben Faktenbestand zwei Profile bedienen. Für die Demo kann der Code die Aussagen aus kurzen, geprüften Textbausteinen zusammensetzen. Jede Zeile bekommt mindestens eine Artikel-ID. Quellen-URLs kommen aus dem eingelesenen Artikel. Fehlt eine Quelle, die Aussage vor der Audioerzeugung weglassen.
5. **Audio und Anzeige.** Pro Profil denselben geprüften Text als Transkript und Eingabe für ElevenLabs verwenden. Im lokalen Browser Profil, Player und anklickbare Quellenlinks direkt je Transkriptzeile zeigen. Zeitstempel wären ein Bonus. Spielt bei erneuter Auswahl die vorhandene Ausgabe ab.

**Gemeinsame Übergabe.** Ein Lauf liefert pro Profil eine MP3 und ein JSON-Objekt mit `profile`, `audioPath` und `claims`. Jeder Eintrag in `claims` enthält `text` und `sources` mit `articleId`, `publisher` und `url`. Interne Belegstellen und Volltexte bleiben beim Prüfschritt. Frühe UI-Testdaten als „Beispieldaten“ kennzeichnen.

## Drei Personen und der Fahrplan

| Rolle | Verantwortlich für | Erste überprüfbare Übergabe |
|---|---|---|
| Daten und Vertrauen | Download, Einlesen, Themenbündel, Fakten mit Belegen und Zahlenprüfung | Ein Ereignis mit zwei Artikeln und zwei geprüften Aussagen |
| Ablauf und Audio | Lokaler Start, OpenAI, ElevenLabs, n8n nur optional am Schluss, Verbrauch messen | Ein kurzes gesprochenes Briefing aus einer echten Meldung |
| Oberfläche und Abgabe | Profilwahl, Player, Quellen pro Aussage, GitHub/BuilderBase koordinieren, Video | Zwei auswählbare Profile mit Beispiel-JSON und klickbaren Links |

Die drei Personen ordnen sich die Rollen beim Kick-off zu. Jede Rolle prüft anschließend die Übergabe einer anderen.

**Vorschlag für die Verteilung (20.11. 15:40, Team bestätigt):** Die Pipeline steht im Rohbau (`src/`, `prepare.py`, `app.py`, siehe README).

| Wer | Teil | Dateien | Konkret bis Fr 18:00 |
|---|---|---|---|
| Matthias (mit Claude Code) | Pipeline: Daten, Bündeln, Fakten, Prüfung, Skript, Kosten | `src/`, `prepare.py`, `one_story.py` | Ganzen Tag vorbereiten, Skript natürlicher, Widersprüche zuverlässig, Kosten 1× und 10× messen |
| Danni | Oberfläche und Klang | `web/` (React + Vite), Branch `audio-ui` | Responsive Player: Satz beim Abspielen hervorheben, Quellenkarte je Aussage, Wildcard-Hörer über die API, Stimme EN und DE auswählen, Audio gegenhören |
| Naomi (Lead) mit Matthias | Produkt, Pitch, Video, Abgabe | Folien, Video, Branch `pitch` | Käufer und Redaktionsablauf, Kostenfolie, Pitch-Skript, 3-Minuten-Video, BuilderBase-Abgabe |

Gegenseitig prüfen: Danni hört die Fakten gegen, Naomi probiert die App wie die Jury, Matthias prüft die Zahlen auf den Folien.
Schnittstelle zwischen Pipeline und Oberfläche: die API in `api.py` (`POST /api/briefing`, Format im README). Danni ändert nur `web/`, Matthias den Rest (auch `src/tts.py`, seit 20.11. 16:20), so gibt es keine Konflikte. `app.py` (Streamlit) bleibt als Ersatz, bis `web/` läuft.

**Entscheidungen 20.11. 16:20** (Sourcera nicht erreichbar, darum selbst entschieden):
- **Zeitfenster:** Artikel vom 13. bis 18.11., das Briefing gilt für den Morgen des 19.11. Grund: so liegen mehrere Tage einer laufenden Story zusammen, und die Jury-Musterlösung bündelt vermutlich über Tage.
- **Dannis Vorschlag 1 (React-Seite, Satz hervorheben, Quellenkarte):** übernommen, React + Vite in `web/` (entschieden 20.11. 16:40; Streamlit hat Verzögerung bei jedem Klick und kann den Satz nicht synchron zum Ton hervorheben). Jede Zeile in `claims` hat jetzt `start`/`end` in Sekunden und je Quelle `quote`, `publisher`, `date`, `evidenceUrl`. Die Quelle in einem neuen Tab öffnen, damit der Player weiterläuft. Öffentlicher Link mit QR-Code: erst nach Freigabe durch Naomi (öffentlicher Deploy).
- **Vorschlag 2 (einmal aufbereiten, je Hörer nur Auswahl und Skript):** so gebaut. Bündeln bleibt Code (TF-IDF) plus ein Modellaufruf über die Titel; deutsche und niederländische Artikel sind Invezz-Übersetzungen und werden über Autor und Uhrzeit verknüpft, dafür braucht es keine Embeddings. Ob `gpt-5.4-nano`/`-mini` (beide bei unserem Schlüssel verfügbar) besser oder billiger sind als `gpt-4.1-mini`, messen wir im Vergleich, bevor wir wechseln.
- **Vorschlag 3 (n8n, ElevenLabs mit Zeitmarken, Cache):** Zeitmarken und Cache sind gebaut (`/with-timestamps`, ein Aufruf). Die Schlüssel bleiben auf dem Server (`api.py`). n8n nur als optionaler Zeitplan am Schluss, weil die Prüfung im Python-Code liegt.
- **Stimme und Ton:** sehr energiegeladen und wach machend (Matthias, 20.11. 16:18 und 16:40). Stimme `eleven_v3`, Einstellung "creative". Skript von `gpt-5.4-mini` als begeisterter Morgenmoderator, ohne Floskeln ("Next up", "Weiter geht es" streicht der Code). Die Energie steckt im Ton, nie in den Fakten: dramatische Verben und Superlative nur, wenn das Zitat sie hat.
- **Prüfung in drei Stufen** (20.11. 16:45, nach dem Gegenlesen): (1) Code: jede Zahl, jeder Superlativ aus dem Zitat, jede Zeile mit Quelle; (2) ein zweites Modell legt jede Zeile neben ihre Zitate und streicht Richtung, Ursache, Geldtipps und "heute/gestern", die die Quelle nicht hergibt; (3) Länge per Code.
- **Zusammenführen** (20.11. 16:50): Das Modell schlägt Gruppen vor, oft eine Riesengruppe mit 200 Storys. Der Code teilt jede Gruppe selbst: Eine Story kommt nur zu einer anderen, wenn beide Titel denselben seltenen Eigennamen tragen ("Huang" ja; "Trump", "Nvidia" zu häufig; Vornamen wie "Donald" nie). Die Obergrenze für Gruppen (16:30) ist wieder raus, weil sie die richtigen Treffer mit verworfen hat.

| Wann (Ortszeit) | Ergebnis |
|---|---|
| **Fr, erste 20 Minuten** | Rollen und Datenstruktur kurz abstimmen. Eine Person prüft BuilderBase/Abgabe und Zugänge, eine die Feeds und Lizenzfragen, eine das bestehende oder neue private Repo. |
| **Fr, innerhalb von 90 Minuten** | Eine echte Meldung komplett durchspielen. Satz, Quelle, Audio und Browseranzeige müssen zusammenpassen. Danach erst die zweite Ausgabe und weitere Daten hinzufügen. |
| **Fr, bis 18:00** | Beide Profile, mindestens ein zusammengeführtes Ereignis, richtige Quellenlinks. Einen vollständigen Durchlauf und Fehlerfälle prüfen. |
| **Fr Abend** | Kosten mit einer Stichprobe hochrechnen, 3-Minuten-Pitch aufnehmen und zwei gelungene Ausgaben lokal für die Vorführung bereithalten. Wenn sie als Ersatz abgespielt werden, im Pitch als vorab erzeugt kennzeichnen. |
| **Sa, 08:30–09:30** | Eine frische Prüfung von Installation, Demo, README und Pitch. Jede gesprochene Zahl gegentesten. Inhalte und Code auf demselben Stand festhalten. |
| **Sa, bis 10:00** | In BuilderBase abschicken und Eingang, Teameintrag und Abspielbarkeit prüfen. 30 Minuten Puffer bis 10:30. |

**Fertig für die Abgabe.** Ein anderes Teammitglied kann laut README starten und zur echten Demo gelangen. Zwei Ausgaben erzeugen und anhören. Für jeden Fakt öffnet sich der Originalartikel; mindestens eine Zahl mit Einheit und Zeitraum ist im Pitch sichtbar geprüft. Ein fehlerhafter Artikel oder fehlgeschlagener Audioaufruf bekommt eine verständliche Meldung. Die Demo-Ausgaben, der Video-Ausschnitt und der abgegebene Code passen zusammen.

## Kostenfolie und Pitch

**Vorrechnung, noch kein Messergebnis.** Nehmt nach dem ersten Test 20–40 Artikel als Stichprobe. Messt OpenAI-Eingabe- und Ausgabetokens sowie die ElevenLabs-Zeichen für die Sprechertexte. Tokens sind die Texteinheiten, nach denen das Modell abrechnet. Gebt die Anzahl Audioausgaben, Wiederholungen, n8n-Ausführungen und Infrastruktur gesondert an.

| Annahme | 1.740 Artikel | 17.400 Artikel |
|---|---:|---:|
| Fakten aus allen Artikeln, je 1.200 Eingabe- und 200 Ausgabetokens | 1,39 USD | 13,92 USD |
| Zwei profilbezogene Skripte zusammen, zusätzlich 6.000 Eingabe- und 1.200 Ausgabetokens | unter 0,01 USD | unter 0,01 USD |
| Zwei Ausgaben mit zusammen 2.400 Sprechertext-Zeichen | 1.200–2.400 ElevenLabs-Credits | 1.200–2.400 ElevenLabs-Credits |

Das Textbeispiel rechnet mit veröffentlichten GPT‑4.1-mini-Referenzpreisen von 0,40 USD pro Million Eingabetokens und 1,60 USD pro Million Ausgabetokens. Für den Pitch das tatsächlich verfügbare Modell und den gemessenen Verbrauch einsetzen. Die ElevenLabs-Spanne gilt für unterstützte Flash/Turbo-API-Modelle, den Eventtarif separat prüfen. Bei zehnmal so vielen Artikeln bleiben die Audio-Kosten in diesem Szenario gleich, weil weiterhin zwei gleich lange Ausgaben erzeugt werden. Bei zehnmal so vielen individuellen Ausgaben steigen sie entsprechend. n8n-Tarif und Hosting getrennt ergänzen, sobald das Setup feststeht. [OpenAI-Preise](https://developers.openai.com/api/docs/pricing) · [ElevenLabs-Preise](https://elevenlabs.io/pricing)

**Pitch-Vorschlag für drei Minuten.**

- **0:00–0:25** Viele Menschen haben morgens wenig Zeit. Finanzredaktionen wollen relevante Updates liefern und ihre Quellen sichtbar halten.
- **0:25–1:25** Zwei kurze Audioausschnitte aus demselben Nachrichtentag vorspielen und die unterschiedlichen Themen zeigen.
- **1:25–2:00** Eine gehörte Zahl im Transkript aufrufen. Originalquelle öffnen, Zahl und Kontext zeigen. Zwei Artikel zu einer Story bündeln.
- **2:00–2:40** Käufer und Ablauf erklären. Eine Redaktion bereitet die Quellen einmal auf, prüft und veröffentlicht dann mehrere Briefings.
- **2:40–3:00** Vollmenge und 10× auf einer Folie zeigen. Schlusssatz: „Dieselben Nachrichten. Zwei persönliche Briefings. Jede Aussage führt zur Quelle.“

## Fragen für den Start

- **Zuerst mit Matthias klären:** zweites festes Demo-Profil auf Deutsch (Empfehlung, Begründung oben in der Profiltabelle) oder auf Englisch (Trader und Einsteiger)? Die Sprache bleibt so oder so eine Einstellung für den Wildcard-Hörer.

- Welche drei Personen übernehmen die Rollen, und gibt es bereits ein privates GitHub-Repo? Wenn ja, beim Klonen die zwei Planungsdateien in diesem Ordner sichern und anschließend in den Checkout übernehmen. `git clone` braucht einen leeren Zielordner.
- Welchen Zugriff hat die Jury auf Code und Video, und gelten im Sourcera-Track zusätzliche Felder oder Vorgaben? Im BuilderBase-Formular prüfen.
- Öffnet der Sourcera-Download im Eventbrowser? Welche Verarbeitung und Videoausschnitte sind im Rahmen der Datennutzung zulässig? Bei Unklarheit Sourcera oder den Tech-Support vor Ort fragen.
- Wie werden API- und n8n-Credits angerechnet? Erste Testaufrufe klein halten und Verbrauch protokollieren.

Grundlage sind „MAIN Summit - Challenge Track“, Sourcera-Abschnitt (PDF-Seiten 11–19), „Getting started with BuilderBase“, insbesondere Seiten 4–11, und der Download-Link aus „Sourcera-Data-Link“.
