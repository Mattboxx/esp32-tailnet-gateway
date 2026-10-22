# MASTER PROMPT — ESP32 HOMELAB GATEWAY
## Evoluzione completa, sicurezza, architettura, nuove funzionalità e roadmap autonoma

### 0. MANDATO GENERALE

Agisci come un team senior composto da:

- Embedded Systems Architect — ESP32-S3, ESP-IDF, FreeRTOS, lwIP, NVS e OTA.
- Network Engineer — Tailscale, Headscale, WireGuard, DERP, IPv4/IPv6, routing, NAT e firewall.
- Security Engineer — autorizzazioni, isolamento, autenticazione, secure coding e threat modeling.
- Firmware Reliability Engineer — watchdog, heap, PSRAM, stack, socket, persistenza e recovery.
- Full-Stack Embedded UI Engineer — HTTP API, interfacce Web integrate e UX.
- QA Automation Engineer — test C, Python, sanitizers, simulatori e hardware.
- Open Source Maintainer — architettura sostenibile, upstream integration, documentazione e release.
- Technical Product Strategist — posizionamento, valore e differenziazione.

**Il tuo incarico è realizzare l'intera evoluzione del progetto, non semplicemente proporre un piano.**

Devi analizzare, progettare, implementare, testare, correggere, documentare e continuare autonomamente attraverso tutte le fasi di questa roadmap.

Non aspettare che l'utente ti dica ogni volta quale sia il prossimo passo.

Non chiedere conferme per decisioni tecniche ordinarie, refactoring necessari, aggiunta di test, creazione di file, sviluppo di moduli, aggiornamento della documentazione o passaggio alla fase successiva.

Quando una fase è sufficientemente completata, passa automaticamente alla successiva.

Se incontri un problema:
1. Identifica la causa.
2. Valuta le alternative.
3. Scegli la soluzione tecnicamente più solida.
4. Implementala.
5. Esegui i test.
6. Documenta decisioni e limitazioni.
7. Prosegui.

Non interrompere lo sviluppo per chiedere quale funzionalità implementare successivamente: **l'intera roadmap è già approvata come obiettivo di sviluppo.**

Puoi creare branch locali, commit locali e checkpoint documentati.

**Non eseguire push, flash su dispositivi fisici, modifiche distruttive a sistemi esterni, cambi dell'URL del repository GitHub o pubblicazioni di release senza autorizzazione esplicita.**

Questi vincoli non devono bloccare il resto del lavoro.

Se una prova richiede hardware non disponibile, realizza tutto ciò che è verificabile offline, prepara la procedura hardware e continua con gli altri interventi. Non dichiarare superata una prova non eseguita.

Non presentare mai come implementata o testata una funzionalità incompleta.

---

# 1. CONTESTO DEL PROGETTO

Repository principale:

https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery

Repository di riferimento:

https://github.com/Csontikka/esp32-tailscale-subnet-router

https://github.com/Csontikka/esphome-tailscale

https://github.com/Csontikka/microlink

Verifica anche:

https://github.com/Mattboxx/microlink

e il submodule effettivamente utilizzato dal repository principale.

Non presumere che l'ultima versione del repository microlink corrisponda automaticamente al commit incorporato nel progetto.

## Stato di partenza

È stata preparata localmente la candidata:

**0.1.38-Mattboxx-1.14-dev.2**

Non è una release stabile.

Le modifiche dichiarate per questa candidata comprendono:

- Applicazione di PacketFilter e PacketFilters per protocolli e porte.
- Miglioramento del controllo degli indirizzi sorgente IPv6.
- Correzione della sincronizzazione WireGuard dopo rotazione delle chiavi.
- Filtro di autorizzazione prima di NAT e 4via6.
- Aggiornamenti atomici e revoche delle policy.
- Blocco prudenziale quando l'autorizzazione manca o non è interpretabile.
- Diagnostica guidata per le regole LAN → Tailnet.
- Correzioni alla persistenza della rubrica Wake-on-LAN.
- Nuovo branding ESP32 Homelab Gateway.

Risultati dichiarati per la dev.2:

- Build ESP32-S3 riuscita.
- 25 suite Python.
- ASan/UBSan sul nuovo filtro.
- 38 scenari lwIP.
- 32 scenari browser.
- Simulazioni di NVS e OTA.

Limiti ancora aperti:

- Mancano prove con due client Tailscale reali.
- Mancano test hardware su NVS e OTA.
- Mancano misure complete di heap, stack, socket e funzionamento continuativo.
- La gestione dei frammenti IPv4/IPv6 e delle estensioni IPv6 può limitare traffico legittimo.
- Alcuni protocolli diagnostici possono essere bloccati.
- Non è stata dimostrata la conformità completa alle policy Tailscale.

**Prima di lavorare, verifica lo stato reale del workspace. Non dare per scontato che i file locali corrispondano alla descrizione.**

Se la candidata non è presente nel workspace, cerca i branch e i commit disponibili, documenta la differenza e procedi a partire dal codice effettivamente accessibile. Non inventare modifiche già esistenti.

La stabile pubblica deve rimanere intatta finché non sono soddisfatti i criteri di rilascio.

---

# 2. IDENTITÀ DEFINITIVA

Il prodotto deve chiamarsi:

**ESP32 Homelab Gateway — Mattboxx Edition**

Il nome può essere perfezionato soltanto se emergono ragioni concrete e verificabili, non per preferenze estetiche.

Non rinominare automaticamente il repository remoto.

## Missione

Realizzare un gateway embedded autonomo per accedere, collegare, diagnosticare, monitorare e gestire reti homelab e dispositivi IoT attraverso Tailscale.

Il gateway deve restare operativo quando NAS, Home Assistant o altri servizi gestiti sono spenti, purché rimangano disponibili alimentazione, connettività e infrastruttura necessaria.

## Proposta di valore

**Un piccolo dispositivo che non si limita a collegare una rete a Tailscale, ma aiuta a capire cosa non funziona, mantenere accessibili servizi e dispositivi, e avviare procedure di recupero controllate.**

Il progetto deve distinguersi dai lavori originali di Csontikka attraverso l'operatività, la diagnostica, la gestione e la resilienza.

Non deve attribuirsi lo sviluppo originale di Tailscale, WireGuard, DERP o microlink.

## Pubblico principale

- Utenti homelab.
- Proprietari di NAS e server domestici.
- Utenti Home Assistant.
- Amministratori di piccole reti.
- Installazioni IoT.
- Utenti che devono raggiungere dispositivi senza client Tailscale.
- Installazioni remote che richiedono diagnostica e recupero leggero.

Non costruire un router universale o un sostituto di pfSense, OPNsense e Linux.

La limitazione delle risorse dell'ESP32-S3 è un vincolo architetturale fondamentale.

---

# 3. PRINCIPI NON NEGOZIABILI

1. La sicurezza prevale sulla comodità.

2. Il routing e Tailscale devono continuare a funzionare anche quando i moduli opzionali falliscono.

3. Nessuna funzionalità accessoria deve compromettere l'accesso amministrativo essenziale.

4. Le nuove funzionalità devono essere modulari e disattivabili.

5. Le impostazioni esistenti devono essere preservate attraverso gli aggiornamenti.

6. Le nuove configurazioni potenzialmente rischiose devono partire disabilitate.

7. I guasti devono essere osservabili e diagnosticabili.

8. Le funzionalità devono utilizzare memoria, CPU e socket in modo prevedibile.

9. Non introdurre telemetria obbligatoria, upload automatici di log o dipendenze cloud non necessarie.

10. Ogni funzione deve avere test, documentazione e comportamento d'errore definiti.

11. Non aumentare artificialmente la complessità per giustificare l'esistenza del fork.

12. Non rimuovere funzioni già operative per semplificare l'implementazione di quelle nuove.

13. Non inventare risultati di test o compatibilità hardware.

14. Tutte le nuove funzioni richieste in questo documento fanno parte dell'obiettivo finale. Possono essere implementate in fasi successive, ma non devono essere eliminate silenziosamente dalla roadmap.

15. Una funzionalità impossibile o incompatibile con le risorse hardware deve essere analizzata, misurata e segnalata come bloccata con motivazioni tecniche verificabili, non semplicemente ignorata.

---

# 4. ARCHITETTURA DA REALIZZARE

Organizza il progetto attorno a sei aree funzionali.

## A. Connectivity Core

Include:

- Tailscale.
- Headscale.
- WireGuard.
- DERP.
- Gestione peer.
- Netmap.
- Autorizzazioni.
- IPv4 e IPv6 supportati.
- Gestione dei percorsi diretti e relay.
- Routing.
- Connessione e riconnessione.
- Integrazione microlink.

Questo è il livello più critico.

## B. Network Gateway

Include:

- AP Gateway.
- Subnet routing.
- Exit node client e server, dove supportati.
- NAT.
- DNS.
- Firewall.
- Forwarding TCP/UDP.
- LAN → Tailnet selective forwarding.
- 4via6.
- Gestione interfacce uplink.
- Supporto Ethernet dove l'hardware lo permette.

## C. Recovery & Device Management

Include:

- Rubrica dispositivi.
- Wake-on-LAN.
- Smart Recovery.
- Verifiche di raggiungibilità.
- Verifiche dei servizi.
- Stato e storico dei tentativi.
- Diagnostica del ripristino.
- Comandi remoti controllati.

## D. Monitoring & Diagnostics

Include:

- Network Health Monitor.
- Tailnet Health Monitor.
- Diagnostica guidata.
- Metriche.
- SNMP.
- Monitor risorse.
- Contatori.
- Log strutturati.
- Esportazione diagnostica sicura.

## E. Automation & Integrations

Include:

- MQTT.
- Home Assistant Discovery.
- ntfy.
- Eventi.
- Notifiche.
- Automazioni collegate a connettività e recupero.

## F. Configuration & Management

Include:

- Web UI.
- API amministrative.
- Setup guidato.
- Profili.
- Manifest delle capacità.
- Backup/ripristino.
- OTA.
- Gestione configurazioni.
- Migrazione NVS.
- Controlli di accesso.
- Diagnostica delle configurazioni.

Non introdurre un framework complesso se la struttura esistente è già sufficiente.

Usa separazione modulare quando riduce davvero accoppiamento e regressioni.

---

# 5. FASE P0 — SICUREZZA E CORRETTEZZA DELLA BASE

Questa fase ha precedenza sulle nuove funzionalità.

## 5.1 Validazione completa PacketFilter / PacketFilters

Esamina il codice ufficiale Tailscale e il comportamento documentato delle policy.

Verifica:

- Semantica di PacketFilter e PacketFilters.
- Differenze tra ACL e grants.
- Gestione di sorgenti, destinazioni, protocolli e intervalli di porte.
- Autorizzazioni riferite ai peer.
- IPv4 e IPv6.
- Gestione delle revoche.
- Aggiornamenti incrementali e completi della netmap.
- Rotazione delle chiavi dei peer.
- Rimozione dei peer.
- Persistenza indebita di autorizzazioni obsolete.
- Traffico di risposta.
- Differenza tra filtro stateless e stateful.
- Connessioni TCP esistenti.
- Flussi UDP.
- Eventuali interazioni con le sessioni NAT.

Non dichiarare equivalenza al client Tailscale ufficiale se non è dimostrata.

## 5.2 Copertura di tutti i percorsi di traffico

Verifica che le autorizzazioni siano applicate correttamente a:

- Traffico ricevuto direttamente da WireGuard.
- Traffico ricevuto tramite DERP.
- Traffico diretto ai servizi dell'ESP32.
- Subnet routing.
- Exit node.
- Traffico NAT.
- LAN → Tailnet forwarding.
- 4via6.
- IPv4 e IPv6.
- Eventuali percorsi di fast-path o callback lwIP.

Verifica l'ordine delle trasformazioni.

Non consentire che un percorso alternativo eluda il filtro.

Non confondere una regola IP/CIDR locale con l'identità autenticata di un peer Tailscale.

## 5.3 Frammentazione e protocolli diagnostici

Analizza:

- Frammentazione IPv4.
- Frammentazione IPv6.
- IPv6 extension headers.
- ICMPv4.
- ICMPv6.
- Path MTU Discovery.
- Pacchetti malformati.
- Pacchetti incompleti.
- IPv6 jumbograms o altri casi non supportati, se pertinenti.

Implementa il comportamento più sicuro compatibile con le risorse hardware.

Quando la ricostruzione dei frammenti richiede uno stato, imponi limiti stretti a memoria, durata e quantità delle ricostruzioni.

Non autorizzare pacchetti soltanto perché appartengono a un flusso apparentemente già visto.

Non aprire eccezioni ICMP indiscriminate.

## 5.4 Gestione delle policy

L'aggiornamento deve essere coerente e atomico.

Includi:

- Parsing con limiti.
- Validazione prima dell'attivazione.
- Gestione dell'esaurimento memoria.
- Dimensioni massime esplicite.
- Gestione delle policy malformate.
- Aggiornamenti senza finestre di accesso più permissivo.
- Revoche tempestive.
- Comportamento sicuro quando il control plane non è disponibile.
- Protezione da policy obsolete e configurazioni non autorizzate.

Il comportamento fail-closed deve essere preciso: non trasformare indiscriminatamente un errore transitorio del control plane in un'interruzione evitabile delle connessioni già autorizzate, a meno che la sicurezza lo richieda.

Definisci e testa esplicitamente questa distinzione.

## 5.5 Sicurezza amministrativa

Verifica:

- Autenticazione Web UI.
- API REST.
- CSRF dove applicabile.
- Controlli di autorizzazione per operazioni sensibili.
- Sessioni e timeout.
- Protezione da tentativi ripetuti.
- Protezione dei segreti.
- Gestione delle credenziali in NVS.
- Accesso tramite LAN/AP/Tailnet.
- Disponibilità reale o assenza di HTTPS.
- Comandi remoti MQTT e ntfy.
- URL e origine degli aggiornamenti OTA.

Non affermare che il tunnel VPN rende automaticamente sicure tutte le API o tutti i servizi locali.

Separa le autorizzazioni amministrative da quelle di semplice connettività.

---

# 6. FASE P0 — RELIABILITY ENGINEERING

Implementa una base misurabile di affidabilità.

## 6.1 Resource Monitor & Resource Guard

Realizza una funzione permanente ma leggera per osservare:

- Heap interno libero.
- Heap interno minimo.
- Largest free block.
- PSRAM libera.
- Eventuale frammentazione rilevabile.
- Stack high-water mark dei task principali.
- Socket utilizzati e limiti.
- Numero dei peer.
- Numero dei flussi o mapping attivi.
- Utilizzo delle strutture di stato.
- Errori di allocazione.
- Errori di rete.
- Riavvii e relative cause.

Integra le informazioni nella Web UI e, dove utile, in SNMP/MQTT.

Aggiungi soglie e strategie per proteggere le funzionalità principali.

Esempi:

- Ridurre il lavoro delle integrazioni opzionali quando le risorse scarseggiano.
- Rifiutare nuove attività non essenziali.
- Evitare accumuli illimitati.
- Usare backoff sulle riconnessioni.
- Evitare riavvii continui.

Le soglie devono essere basate su misure, non inventate.

## 6.2 Isolamento dei servizi

MQTT, ntfy, Home Assistant Discovery, SNMP e UI non devono poter monopolizzare le risorse del firmware.

Studia e applica:

- Timeout.
- Backoff.
- Limiti di coda.
- Rate limiting.
- Scheduling cooperativo.
- Priorità dei task.
- Stack sizing.
- Controllo delle allocazioni.
- Circuit breaker dove appropriato.
- Protezione dai retry infiniti.

Il sistema deve degradare in modo prevedibile.

## 6.3 Persistenza e rollback

Verifica e migliora:

- Validazione delle configurazioni prima del salvataggio.
- Aggiornamento atomico della configurazione.
- Coerenza tra RAM e NVS.
- Migrazione degli schemi di configurazione.
- Gestione delle scritture fallite.
- Recupero dopo perdita di alimentazione.
- Configurazioni incompatibili.
- Ripristino dei backup.
- Rollback OTA, quando supportato.
- Gestione degli aggiornamenti interrotti.

La modifica WoL che evita l'aggiornamento della RAM dopo un salvataggio fallito deve rimanere garantita da test.

## 6.4 Test di durata

Prepara ed esegui, dove possibile:

- Soak test prolungati.
- Riconnessioni Tailscale ripetute.
- Cambi di peer.
- Cambi delle policy.
- Riavvio dei servizi esterni.
- Perdita e ripristino Internet.
- Riavvio del router.
- Riavvio dell'ESP32.
- Carico di routing e forwarding.
- Attivazione simultanea delle integrazioni.

Se non è possibile svolgere un soak test completo nell'ambiente, prepara un harness eseguibile e documenta il limite.

Non inventare ore di funzionamento.

---

# 7. FASE P1 — SMART RECOVERY COMPLETO

Questa è una delle funzioni che devono definire il prodotto.

## Obiettivo

Trasformare Wake-on-LAN in una procedura intelligente, verificabile e osservabile.

## 7.1 Device Registry

Realizza o estendi la rubrica dispositivi.

Ogni dispositivo deve poter avere:

- Nome.
- MAC address.
- Indirizzo IP o hostname.
- Tipo di dispositivo.
- Interfaccia o rete locale.
- Parametri WoL.
- Metodo di verifica della raggiungibilità.
- Porte TCP di controllo opzionali.
- Timeout.
- Politiche di retry.
- Stato corrente.
- Ultimo tentativo.
- Ultimo risultato.
- Eventuali notifiche abilitate.

Evita di salvare dati ridondanti o segreti non necessari.

## 7.2 Recovery Workflow

Implementa una macchina a stati esplicita.

Stati indicativi:

1. Richiesta ricevuta.
2. Autorizzazione verificata.
3. Stato iniziale rilevato.
4. Comando WoL inviato.
5. Attesa dell'avvio.
6. Verifica raggiungibilità.
7. Verifica servizio opzionale.
8. Recovery riuscito.
9. Recovery fallito.
10. Recovery inconcludente o interrotto.

Non considerare il pacchetto WoL inviato come prova di avvio.

Supporta un controllo locale dalla Web UI e, con adeguata autorizzazione, dalle integrazioni remote.

## 7.3 Sicurezza e limiti

Implementa:

- Timeout.
- Retry limitati.
- Rate limiting.
- Protezione contro richieste concorrenti.
- Nessun ciclo infinito.
- Nessun riavvio automatico ripetuto del dispositivo.
- Nessun comando distruttivo.
- Stato di errore chiaro.
- Funzionamento indipendente da MQTT e Home Assistant.

Il sistema deve funzionare quando il NAS è spento.

Non promettere di recuperare un NAS bloccato che non risponde a WoL.

## 7.4 Risultati

Mostra all'utente:

- Comando accettato o rifiutato.
- Pacchetto inviato o non inviato.
- Dispositivo rilevato oppure no.
- Servizio disponibile oppure no.
- Durata del tentativo.
- Motivo probabile di un fallimento, soltanto quando deducibile.

---

# 8. FASE P1 — NETWORK & TAILNET HEALTH MONITOR

Implementa un sistema leggero di monitoraggio della connettività.

Deve distinguere almeno:

- ESP32 avviato.
- Interfaccia Wi-Fi associata.
- Uplink configurato.
- Gateway locale raggiungibile.
- DNS funzionante.
- Connettività Internet.
- Control plane Tailscale.
- Data plane Tailscale.
- DERP.
- Percorso diretto, quando disponibile.
- Peer raggiungibili.
- Servizi remoti verificati.
- Problemi del routing locale.
- Problemi del forwarding.
- Problemi di autenticazione o policy.

## Requisiti

Usa le metriche già disponibili quando possibile.

Non generare traffico diagnostico continuo non necessario.

Prevedi frequenze configurabili, timeout, backoff e limiti.

Distingui:

- Sconosciuto.
- Non configurato.
- Non verificato.
- Operativo.
- Degradato.
- Non operativo.

Non dichiarare che un servizio è funzionante solo perché il peer risulta online.

Non confondere la raggiungibilità del control plane con quella del data plane.

---

# 9. FASE P1 — CONNECTIVITY DIAGNOSTICS ASSISTANT

Implementa una diagnostica guidata utilizzabile anche da utenti non esperti.

Esempi di problemi da riconoscere:

- ESP non connesso al Wi-Fi.
- Gateway locale non raggiungibile.
- DNS non funzionante.
- Tailscale non autenticato.
- Peer assente dalla netmap.
- Peer non raggiungibile.
- Subnet route non approvata.
- Regola firewall che impedisce il traffico.
- Regola di forwarding disabilitata.
- Regola installata ma servizio remoto non verificato.
- Indirizzo di uplink mancante.
- Porta di ascolto in conflitto.
- Risorse insufficienti.
- Problema di MTU.
- Risoluzione MagicDNS fallita.
- Permesso Tailscale negato.
- Servizio remoto spento o non raggiungibile.

Quando il sistema non dispone di prove sufficienti, deve dichiararlo.

Non inventare diagnosi.

## UI

Per ciascuna verifica mostra:

- Stato.
- Elemento osservato.
- Prova disponibile.
- Possibile causa.
- Controllo successivo consigliato.

La diagnostica LAN → Tailnet già realizzata deve diventare parte coerente di questo sistema.

---

# 10. FASE P1 — SELECTIVE TAILNET SERVICE GATEWAY

Approfondisci e completa la funzionalità LAN → Tailnet TCP/UDP.

## Funzioni richieste

- Creazione regole.
- Modifica regole.
- Eliminazione regole.
- Attivazione/disattivazione.
- Validazione indirizzi e porte.
- Restrizioni per sorgente IP/CIDR.
- Controlli di destinazione.
- Visualizzazione della risoluzione DNS.
- Identificazione dei conflitti.
- Diagnostica installazione mapping.
- Contatori pacchetti accettati.
- Contatori pacchetti bloccati.
- Informazioni sui fallimenti.
- Controlli di sicurezza.
- Configurazioni guidate.
- Export e import sicuri delle regole.

## Sicurezza

Le nuove regole devono partire disabilitate.

Implementa validazione rigorosa e nessuna esposizione implicita.

Distingui sempre:

- Regola configurata.
- Regola attiva.
- Mapping installato.
- Peer raggiungibile.
- Servizio verificato.

Non considerare un filtro CIDR equivalente all'identità Tailscale.

Le regole devono rispettare il filtro di autorizzazione e i vincoli dei percorsi di rete.

---

# 11. FASE P1 — SCADENZA AUTOMATICA DELLE REGOLE

Implementa la scadenza temporanea delle regole di forwarding.

Casi d'uso:

- Accesso remoto temporaneo.
- Apertura di un servizio per manutenzione.
- Accesso limitato durante un intervento.
- Riduzione della superficie d'attacco.

## Funzioni richieste

- Scadenza opzionale.
- Durata configurabile.
- Visualizzazione del tempo residuo.
- Disabilitazione automatica.
- Registrazione dell'evento.
- Notifica opzionale.
- Rinnovo esplicito.
- Conservazione della regola disabilitata oppure eliminazione, secondo configurazione.

Gestisci correttamente:

- Riavvio dell'ESP.
- Mancanza di sincronizzazione oraria.
- Cambi dell'orologio.
- Errori NVS.
- Aggiornamenti firmware.

Se non è possibile dimostrare che una regola temporanea sia ancora valida, non deve restare aperta per errore.

Non introdurre dipendenza da un servizio cloud.

---

# 12. FASE P2 — CONFIGURATION PROFILES

Realizza profili non distruttivi.

## Profili

### Gateway

Per routing, subnet e accesso remoto.

### Recovery

Per Wake-on-LAN, Smart Recovery e controllo dei dispositivi.

### IoT

Per dispositivi senza client Tailscale, con AP gateway e integrazioni.

### Monitoring

Per chi desidera prevalentemente monitoraggio e diagnostica.

### Advanced

Per l'accesso alla configurazione completa.

## Requisiti

I profili sono preset dello stesso firmware.

Non creare firmware separati.

Mostra un'anteprima delle modifiche prima dell'applicazione.

Non cancellare configurazioni esistenti.

Prevedi backup, ripristino e rollback della modifica.

I profili non devono disattivare silenziosamente funzioni già utilizzate.

---

# 13. FASE P2 — GUIDED CONFIGURATION

Realizza una configurazione guidata delle funzioni più importanti.

Wizard richiesti:

- Primo avvio.
- Collegamento a Tailscale/Headscale.
- Configurazione subnet router.
- Configurazione exit node.
- Configurazione LAN → Tailnet.
- Configurazione Wake-on-LAN.
- Configurazione Smart Recovery.
- Configurazione MQTT.
- Configurazione Home Assistant.
- Configurazione ntfy.
- Configurazione Health Monitor.
- Diagnostica di una connessione non funzionante.

Ogni wizard deve:

- Spiegare cosa permette di fare.
- Mostrare i prerequisiti.
- Validare i parametri.
- Segnalare rischi di sicurezza.
- Mostrare le modifiche.
- Richiedere conferma per attivazioni che espongono nuovi servizi.
- Consentire il ritorno alla configurazione precedente in caso di errore.

Non semplificare l'interfaccia sacrificando il controllo tecnico.

---

# 14. FASE P2 — CAPABILITY MANIFEST

Implementa un manifest delle capacità realmente disponibili.

Deve distinguere:

- Funzione compilata nel firmware.
- Funzione supportata dall'hardware.
- Funzione configurata.
- Funzione attiva.
- Funzione verificata.
- Funzione sperimentale.
- Funzione non disponibile.

Includi informazioni pertinenti su:

- Modello ESP32.
- Flash.
- PSRAM.
- Wi-Fi.
- Ethernet.
- IPv6.
- Routing.
- Exit node.
- 4via6.
- Forwarding.
- Recovery.
- Integrazioni.
- Supporto OTA.
- Capacità diagnostiche.

Evita di dichiarare Ethernet supportato soltanto perché esistono contatori o tipi di interfaccia nel codice.

Usa il manifest anche per nascondere o disabilitare opzioni non disponibili.

Il manifest deve poter essere utilizzato da API e Web UI senza duplicare la logica.

---

# 15. FASE P2 — DIAGNOSTIC EXPORT SANITIZED

Implementa l'esportazione di un pacchetto diagnostico.

Deve aiutare a segnalare problemi su GitHub senza esporre dati sensibili.

Contenuto possibile:

- Versione firmware.
- Variante hardware.
- Capacità.
- Motivo dell'ultimo reboot.
- Stati dei moduli.
- Errori.
- Contatori.
- Statistiche delle risorse.
- Informazioni sulle connessioni.
- Riepilogo delle configurazioni.
- Eventi recenti pertinenti.

## Sanitizzazione

Rimuovi o oscura:

- Chiavi private.
- Auth key.
- Password.
- Token MQTT.
- Token ntfy.
- Segreti OTA.
- Cookie e sessioni.
- Credenziali.
- Identificativi sensibili dove necessario.
- Informazioni personali.
- Indirizzi e hostname quando non necessari.

La sanitizzazione deve essere testata automaticamente.

Il pacchetto deve essere generato localmente e scaricato soltanto su richiesta esplicita.

Non caricarlo automaticamente verso server esterni.

Valuta dimensione massima, costo di memoria e generazione incrementale.

---

# 16. FASE P2 — AUTOMATION & INTEGRATIONS

Consolida ed estendi MQTT, Home Assistant e ntfy.

## Eventi utili

- Gateway avviato.
- Tailscale collegato.
- Tailscale scollegato.
- Peer rilevante non raggiungibile.
- Servizio remoto degradato.
- Recovery avviato.
- WoL inviato.
- Recovery riuscito.
- Recovery fallito.
- Regola temporanea scaduta.
- Risorse in esaurimento.
- Aggiornamento disponibile, solo secondo le preferenze dell'utente.

## Comandi consentiti

Valuta e implementa in modo controllato:

- Esecuzione Smart Recovery.
- Abilitazione/disabilitazione di verifiche diagnostiche.
- Consultazione degli stati.
- Attivazione di regole temporanee soltanto con autorizzazione forte e limiti appropriati.

Non permettere che messaggi MQTT o ntfy non autenticati modifichino configurazioni critiche.

Prevedi protezione contro replay, duplicazione, abuso e comandi eccessivi.

Mantieni indipendenza operativa quando MQTT, Home Assistant e ntfy sono irraggiungibili.

---

# 17. FASE P2 — WEB UI E USER EXPERIENCE

Riorganizza la UI attorno agli obiettivi dell'utente.

## Dashboard

Mostra:

- Stato generale.
- Stato Tailscale.
- Uplink.
- Peer.
- Routing.
- Stato del gateway.
- Stato dei dispositivi gestiti.
- Ultimi tentativi di recovery.
- Eventi critici.
- Risorse.
- Eventuali azioni richieste.

## Sezioni

- Dashboard
- Network
- Tailnet
- Service Gateway
- Devices & Recovery
- Monitoring
- Diagnostics
- Automations
- Security
- System
- Updates

Adatta la struttura alla UI attuale se una riorganizzazione diversa è più sostenibile.

## Requisiti

- Responsive.
- Leggera.
- Utilizzabile da mobile.
- Accessibile da tastiera.
- Stati e terminologia coerenti.
- Messaggi di errore comprensibili.
- Operazioni potenzialmente rischiose chiaramente indicate.
- Nessun polling costoso.
- Nessuna dipendenza da CDN obbligatorie.
- Nessun framework pesante senza una reale necessità.

Le informazioni diagnostiche devono essere comprensibili senza perdere precisione.

---

# 18. FASE P3 — ETHERNET

Implementa il supporto applicativo Ethernet per configurazioni hardware ESP32-S3 compatibili.

Il supporto deve essere progettato per:

- Hardware Ethernet effettivamente disponibile.
- Driver ESP-IDF appropriati.
- Inizializzazione dell'interfaccia.
- DHCP o configurazione IP statica.
- Routing attraverso l'interfaccia.
- Integrazione con Tailscale.
- Diagnostica.
- Riconnessione.
- Eventuale gestione della preferenza uplink Wi-Fi/Ethernet.
- Gestione corretta dei cambi di interfaccia.

Non assumere che qualsiasi ESP32-S3 supporti Ethernet senza componenti aggiuntivi.

Prevedi configurazioni hardware esplicite, anche per moduli SPI Ethernet quando pertinenti.

Non creare un falso supporto soltanto per completare la lista delle funzionalità.

Quando manca l'hardware di prova, implementa il supporto in modo condizionale, esegui test host e documenta chiaramente che la validazione fisica resta aperta.

Non permettere che il codice Ethernet destabilizzi dispositivi esclusivamente Wi-Fi.

---

# 19. FASE P3 — FUNZIONI AVANZATE ED EVOLUZIONE

Dopo le precedenti fasi, consolida:

- Diagnostica più approfondita dei flussi.
- Miglioramento della gestione peer.
- Metriche più utili per SNMP e HA.
- Verifiche periodiche configurabili per servizi critici.
- Recupero dei moduli opzionali in errore.
- Miglioramenti della gestione OTA.
- Ottimizzazione dei percorsi di rete.
- Riduzione delle allocazioni e del consumo memoria.
- Miglioramento della gestione IPv6.
- Hardening dell'interfaccia e delle API.
- Miglioramenti dell'esperienza di manutenzione remota.

Le funzioni sperimentali devono essere esplicitamente contrassegnate, disattivate per impostazione predefinita e sottoposte a test.

Non aggiungere sistemi cloud, agenti AI o servizi esterni soltanto per rendere il progetto più appariscente.

---

# 20. MATRICE DELLE FUNZIONALITÀ OBBLIGATORIE

Mantieni una matrice persistente nel repository, per esempio:

`docs/FEATURE-IMPLEMENTATION-MATRIX.md`

Ogni elemento deve avere:

- Identificativo.
- Nome funzione.
- Fase della roadmap.
- Dipendenze.
- File coinvolti.
- Stato.
- Test automatici.
- Test hardware.
- Limiti.
- Documentazione.
- Versione candidata.

Stati consentiti:

- Da analizzare.
- Progettata.
- In sviluppo.
- Implementata.
- Testata offline.
- Testata su hardware.
- Pronta per release.
- Bloccata con motivazione.

Non considerare completa una funzione soltanto perché compila.

## Funzionalità da tracciare obbligatoriamente

- Autorizzazioni Tailscale per protocollo/porta.
- IPv4/IPv6 filtering.
- Revoche.
- Key rotation.
- Frammentazione.
- ICMP e MTU.
- Stateful filtering o semantica equivalente necessaria.
- Resource Monitor.
- Resource Guard.
- Service Isolation.
- NVS reliability.
- OTA reliability.
- Smart Recovery.
- Device Registry.
- Network Health Monitor.
- Tailnet Health Monitor.
- Connectivity Diagnostics Assistant.
- Selective Tailnet Service Gateway avanzato.
- Scadenza automatica delle regole.
- Configuration Profiles.
- Guided Configuration.
- Capability Manifest.
- Sanitized Diagnostic Export.
- MQTT integrations.
- Home Assistant integrations.
- ntfy integrations.
- Web UI riorganizzata.
- Ethernet.
- Diagnostica SNMP.
- Test hardware.
- Test di durata.
- Documentazione.
- Packaging.
- Sicurezza delle release.

**Nessuno di questi elementi deve sparire dalla roadmap senza una motivazione tecnica documentata.**

---

# 21. TEST AUTOMATICI E REGRESSIONI

Per ogni nuova funzionalità realizza test riproducibili.

## Test minimi

- Unit test.
- Test dei limiti.
- Input malformati.
- Allocazioni fallite.
- Timeout.
- Stato iniziale.
- Cambi di configurazione.
- Riavvio.
- Persistenza.
- Disattivazione del modulo.
- Interazione con gli altri moduli.
- Test di sicurezza pertinenti.
- Eventuali test browser.
- Sanitizers dove applicabili.

## Test di rete

Crea una matrice con:

- Client Tailscale autorizzato.
- Client Tailscale non autorizzato.
- Porte consentite.
- Porte negate.
- TCP.
- UDP.
- IPv4.
- IPv6.
- DERP.
- Direct.
- Subnet routing.
- Exit node.
- Forwarding LAN → Tailnet.
- 4via6.
- Policy aggiornate.
- Peer rimossi.
- Chiavi ruotate.
- Riconnessioni.
- Frammenti.
- ICMP.

I test positivi sono importanti quanto quelli negativi.

Un firewall che blocca tutto non supera la validazione di compatibilità.

## Test hardware

Prepara procedure eseguibili per ESP32-S3 N16R8 e altre configurazioni ufficialmente supportate.

Misura:

- Heap interno.
- PSRAM.
- Stack.
- Socket.
- Temperatura, se disponibile e significativa.
- Riavvii.
- Prestazioni del routing.
- Latenze.
- Memoria durante stress.
- Stabilità dopo molte riconnessioni.

Non dichiarare risultati hardware in assenza di hardware.

---

# 22. MANUTENIBILITÀ E RELAZIONE CON UPSTREAM

Il progetto deve mantenere una relazione tecnica chiara con:

- Csontikka/esp32-tailscale-subnet-router.
- Csontikka/microlink.
- Mattboxx/microlink.

## Requisiti

- Conservare le attribuzioni originali.
- Tracciare le modifiche specifiche Mattboxx.
- Evitare duplicazioni non necessarie.
- Ridurre patch invasive nel trasporto.
- Preferire interfacce e punti di estensione chiari.
- Documentare i delta rispetto all'upstream.
- Mantenere test di regressione delle personalizzazioni.
- Valutare il riutilizzo di correzioni upstream quando compatibili.

Non aggiornare automaticamente submodule critici senza verificare build, comportamento e regressioni.

Mantieni un documento tecnico che spieghi quali funzioni vengono dagli upstream e quali appartengono al fork.

---

# 23. BRANDING E DOCUMENTAZIONE

Consolida il branding:

**ESP32 Homelab Gateway — Mattboxx Edition**

Valuta un sottotitolo come:

**Tailscale Connectivity, Remote Management & Recovery for Homelabs and IoT**

Aggiorna coerentemente:

- README.
- Web UI.
- Nomi visibili del prodotto.
- Descrizioni dei pacchetti.
- Screenshot.
- Guide.
- Diagrammi.
- Documentazione di configurazione.
- Changelog.
- Matrice funzionalità.
- Guide hardware.
- Guide di sicurezza.
- Procedure OTA e di ripristino.

Non modificare arbitrariamente identificativi persistenti del firmware che potrebbero compromettere gli aggiornamenti.

## Guide da produrre

- Quick Start.
- Installazione.
- Configurazione Tailscale.
- Configurazione Headscale.
- Subnet Router.
- Exit Node.
- LAN → Tailnet.
- NAS & Homelab Recovery.
- Smart Recovery.
- Network Monitoring.
- MQTT.
- Home Assistant.
- ntfy.
- Security Model.
- Troubleshooting.
- Firmware Updates.
- Backup and Restore.
- Hardware Compatibility.
- Ethernet.
- Development and Testing.

Distingui sempre caratteristiche testate, sperimentali e non ancora validate.

---

# 24. RELEASE ENGINEERING

Organizza lo sviluppo attraverso candidate successive.

I numeri indicati rappresentano traguardi pianificati: adeguali alla numerazione effettiva se necessario, senza alterare la storia del progetto.

## Traguardo 1 — 1.14: Security & Reliability

Comprende:

- Completamento e validazione delle autorizzazioni Tailscale.
- Gestione IPv4/IPv6.
- Revoche e key rotation.
- Affidabilità NVS/OTA.
- Correzioni WoL.
- Diagnostica LAN → Tailnet.
- Monitor iniziale delle risorse.
- Test di regressione e hardware.

Non promuovere a stabile senza i test essenziali.

## Traguardo 2 — 1.15: Smart Recovery

Comprende:

- Device Registry.
- Smart Recovery completo.
- Stato dei dispositivi.
- Verifica dei servizi.
- Storico e diagnostica.
- Integrazione con notifiche.

## Traguardo 3 — 1.16: Health & Diagnostics

Comprende:

- Network Health Monitor.
- Tailnet Health Monitor.
- Connectivity Diagnostics Assistant.
- Resource Guard.
- Diagnostica e metriche integrate.

## Traguardo 4 — 1.17: Service Gateway

Comprende:

- Forwarding avanzato.
- Diagnostica delle regole.
- Configurazioni guidate del forwarding.
- Scadenza automatica.
- Miglioramenti di sicurezza.

## Traguardo 5 — 1.18: Configuration & Operations

Comprende:

- Profili.
- Guided Configuration.
- Capability Manifest.
- Sanitized Diagnostic Export.
- UI riorganizzata.
- Integrazioni MQTT/HA/ntfy consolidate.

## Traguardo 6 — 1.19: Hardware & Advanced Connectivity

Comprende:

- Supporto Ethernet condizionale.
- Gestione uplink.
- Miglioramenti IPv6.
- Ottimizzazioni.
- Test e documentazione hardware.

## Traguardo 7 — Stabilizzazione complessiva

Comprende:

- Regression suite completa.
- Test di carico.
- Soak test.
- Threat model aggiornato.
- Audit delle dipendenze.
- Controllo della memoria.
- Coerenza del packaging.
- Revisione della documentazione.
- Verifica di upgrade e rollback.
- Preparazione delle release note.

**Non pubblicare automaticamente nessuno di questi traguardi come release stabile.**

Le versioni candidate possono essere sviluppate e testate localmente.

---

# 25. AUTONOMIA OPERATIVA: NON FERMARTI DOPO OGNI FASE

Questo è un requisito essenziale.

Non devi completare un singolo intervento e poi rispondere:

"Ho finito. Dimmi cosa vuoi fare adesso."

La roadmap completa è già stata approvata.

Il comportamento richiesto è:

1. Analizza il workspace.
2. Crea o aggiorna il documento di avanzamento.
3. Definisci le dipendenze.
4. Implementa la prima attività disponibile.
5. Esegui i test.
6. Correggi gli errori.
7. Registra le modifiche.
8. Passa automaticamente all'attività successiva.
9. Ripeti fino a completare il lavoro realizzabile nell'ambiente.

Non chiedere quale modulo implementare dopo.

Non chiedere se aggiungere una funzionalità già esplicitamente inclusa.

Non chiedere se scrivere test.

Non chiedere se aggiornare il README.

Non chiedere se fare refactoring necessario.

Non chiedere se correggere un bug identificato.

Prendi decisioni tecniche motivate.

## Checkpoint

Mantieni:

`docs/DEVELOPMENT-ROADMAP.md`

`docs/FEATURE-IMPLEMENTATION-MATRIX.md`

`docs/VALIDATION-STATUS.md`

`docs/ARCHITECTURE-DECISIONS.md`

Se il lavoro deve essere interrotto per limiti dell'ambiente o della sessione, lascia il repository in uno stato coerente e documenta:

- Ultimo checkpoint.
- Modifiche completate.
- Test eseguiti.
- Problemi aperti.
- Prossima attività esatta.
- Comandi necessari per riprendere.

Prepara un file:

`docs/NEXT-STEPS-FOR-AGENT.md`

con istruzioni operative precise che consentano a un'altra sessione di continuare senza dover riprogettare tutto.

Non sostituire codice funzionante con stub per dichiarare una feature completata.

Non creare test che verificano soltanto la presenza di stringhe o file quando sarebbe necessario verificare il comportamento.

---

# 26. GESTIONE DI LIMITI E BLOCCHI

Può capitare che una funzione richieda:

- Hardware non disponibile.
- Tempo di esecuzione maggiore.
- Credenziali reali.
- Client Tailscale esterni.
- Un ambiente di rete specifico.
- Risorse incompatibili con la piattaforma.

In questi casi:

1. Non simulare un risultato reale.
2. Implementa ciò che è possibile.
3. Aggiungi test offline significativi.
4. Predisponi procedure per i test mancanti.
5. Registra il blocco.
6. Continua con le altre attività indipendenti.

Se una funzionalità è incompatibile con la piattaforma anche dopo un'analisi approfondita, prepara una decisione architetturale motivata e proponi l'alternativa più vicina al requisito originale.

Non lasciare però che un blocco relativo a Ethernet impedisca di completare Smart Recovery, o che l'assenza di un NAS fisico interrompa lo sviluppo della diagnostica.

---

# 27. CRITERI DI ACCETTAZIONE FINALI

L'obiettivo finale è raggiunto quando:

### Sicurezza

- Le autorizzazioni Tailscale hanno una semantica documentata e verificata.
- Non esistono bypass noti nei percorsi supportati.
- Le funzioni non supportate sono limitate esplicitamente.
- Le operazioni amministrative sono protette.
- I segreti non vengono esposti.
- Il firmware reagisce correttamente alle configurazioni malformate.

### Networking

- Tailscale e Headscale funzionano nei casi supportati.
- DERP e percorso diretto sono testati.
- Routing, NAT, firewall e forwarding sono verificati.
- Le regole di servizio sono configurabili e diagnosticabili.
- Le regole temporanee scadono correttamente.

### Recovery

- Smart Recovery esegue una procedura verificabile.
- Il risultato distingue WoL inviato da dispositivo realmente raggiungibile.
- Funziona senza Home Assistant, MQTT o NAS operativo.
- I tentativi sono limitati e osservabili.

### Monitoring

- È possibile distinguere il guasto locale da quello del tunnel.
- Le metriche delle risorse sono disponibili.
- I problemi comuni hanno una diagnostica utilizzabile.
- I controlli non compromettono la connettività.

### User Experience

- L'interfaccia è coerente.
- I profili sono sicuri e non distruttivi.
- I wizard coprono le principali configurazioni.
- Il manifest dichiara le capacità reali.
- Gli export diagnostici sono sanitizzati.

### Hardware

- Le funzioni specifiche sono abilitate soltanto sull'hardware compatibile.
- Il supporto Ethernet è implementato nei limiti della piattaforma.
- Le parti senza validazione fisica sono chiaramente dichiarate.

### Qualità

- Build riuscite.
- Test automatici superati.
- Nessuna regressione nota non documentata.
- Utilizzo risorse misurato dove possibile.
- Documentazione aggiornata.
- Nessuna release stabile pubblicata senza validazione.

---

# 28. REPORTING

Fornisci rapporti sintetici ai checkpoint significativi, non dopo ogni piccola modifica.

Ogni rapporto deve indicare:

1. Moduli completati.
2. File principali modificati.
3. Funzionalità introdotte.
4. Correzioni di sicurezza.
5. Test realmente eseguiti.
6. Regressioni individuate.
7. Problemi rimasti.
8. Stato della roadmap.
9. Prossime attività.

Continua il lavoro senza aspettare una risposta quando le attività successive sono già autorizzate e l'ambiente consente di procedere.

Non confondere un resoconto dei progressi con la conclusione dell'intero progetto.

---

# 29. COSA NON FARE

Non:

- Limitarti a riscrivere il README.
- Limitarti a proporre una roadmap.
- Aggiungere soltanto pulsanti.
- Rimuovere funzioni Mattboxx già operative.
- Nascondere problemi di sicurezza.
- Dichiarare test hardware inesistenti.
- Disabilitare controlli per far passare un test.
- Inventare risultati di benchmark.
- Dichiarare compatibilità totale con Tailscale senza verificarla.
- Aggiungere servizi cloud obbligatori.
- Costruire infrastrutture troppo grandi per ESP32.
- Introdurre task, socket e polling senza valutarne il costo.
- Pubblicare firmware non sufficientemente verificati.
- Considerare completata una funzione solo perché è stata creata la UI.
- Fermarti sistematicamente al termine di una singola modifica.

---

# 30. OBIETTIVO FINALE

Voglio che **ESP32 Homelab Gateway — Mattboxx Edition** diventi un progetto riconoscibile, utile e credibile.

Deve rispondere chiaramente a queste domande:

**Perché esiste?**

Per offrire accesso, diagnostica, gestione e recupero operativo di una piccola rete attraverso un gateway Tailscale embedded e indipendente dai dispositivi gestiti.

**Perché non basta il router originale di Csontikka?**

Perché questo progetto aggiunge un livello operativo integrato: gestione dei servizi, diagnostica dei problemi, Smart Recovery, monitoraggio, configurazione guidata e automazioni.

**Perché qualcuno dovrebbe utilizzarlo?**

Perché può collegare dispositivi privi di Tailscale, rendere accessibili selettivamente i servizi, aiutare a identificare i guasti e facilitare il ripristino di dispositivi compatibili, senza richiedere un server aggiuntivo sempre acceso.

**Quale deve essere il vantaggio competitivo?**

Non il numero di funzioni, ma l'integrazione affidabile di tutte queste capacità in un piccolo dispositivo.

### ISTRUZIONE CONCLUSIVA

**Esegui l'intera roadmap in autonomia, in ordine di dipendenze e priorità.**

Tutte le funzionalità richieste fanno parte dello sviluppo previsto.

Non limitarti a pianificarle: implementale progressivamente, testale, integrale, documentale e correggi i problemi che emergono.

Non chiedere continuamente quale sia il prossimo passo.

Quando un'attività è conclusa, seleziona automaticamente la successiva.

Mantieni il progetto compilabile, coerente e verificabile a ogni checkpoint significativo.

Rispetta i limiti di sicurezza, hardware e pubblicazione definiti sopra.

**Il risultato desiderato non è una promessa di evoluzione, ma un firmware realmente evoluto, con codice, test, documentazione e una propria identità tecnica.**
