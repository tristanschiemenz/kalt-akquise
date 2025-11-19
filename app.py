import streamlit as st
import pandas as pd
import gspread
import requests
import re
import os
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from google.oauth2.service_account import Credentials
from datetime import datetime

# ############################################################################
# --- SICHERHEITS- & KONFIGURATIONS-KONSTANTEN ---
# ############################################################################

# HINWEIS: FÜR ECHTE APPS SOLLTEN SIE DIESE WERTE IN st.secrets SPEICHERN!
HARDCODED_PASSWORD = st.secrets["app_config"]["password"] 

FILE_INPUT_DEFAULT = 'input.csv'
GSPREAD_SHEET_URL = 'https://docs.google.com/spreadsheets/d/14hxtRmWsTiO8t4G3EEXFNKK19xj5cUDu4nWBtTXPwvI/edit?gid=0#gid=0'
GSPREAD_SHEET_NAME_MAIN = 'Akquise-Kunden' 
GSPREAD_SHEET_NAME_REJECTED = 'Abgelehnt'

GSPREAD_SCOPE = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file'
]

# Regex & Header Config (Unverändert)
# ... (Ihr ursprünglicher Code für TLD_LIST, EMAIL_REGEX, IMPRINT_REGEX, HEADERS folgt hier)
TLD_LIST = r'\.(?:' + \
    r'com|org|net|edu|gov|mil|biz|info|name|mobi|jobs|travel|museum|aero|asia|cat|coop|int|pro|tel|xxx|' + \
    r'de|eu|at|ch|fr|uk|co\.uk|nl|es|it|pl|se|no|dk|fi|ru|ca|us|jp|cn|in|br|au|nz|' + \
    r'ai|io|tv|me|co|ly|to|sh|gg|ag|' + \
    r'academy|accountant|accountants|active|actor|adult|agency|airforce|apartments|app|archi|army|art|' + \
    r'associates|attorney|auction|audio|autos|' + \
    r'band|bank|bar|bargains|bayern|beer|berlin|best|bet|bid|bike|bingo|bio|black|blog|blue|boo|book|' + \
    r'boutique|broker|build|builders|business|buzz|' + \
    r'cab|cafe|cam|camera|camp|capital|car|cards|care|career|careers|cash|casino|catering|center|ceo|' + \
    r'charity|chat|cheap|church|city|claims|cleaning|click|clinic|clothing|cloud|club|coach|codes|coffee|' + \
    r'community|company|compare|computer|condos|construction|consulting|contact|contractors|cooking|cool|' + \
    r'country|coupons|courses|credit|creditcard|cricket|cruises|' + \
    r'dance|data|date|dating|day|deal|deals|degree|delivery|democrat|dental|dentist|design|dev|diamonds|' + \
    r'diet|digital|direct|directory|discount|doctor|dog|domains|dot|download|' + \
    r'earth|eat|eco|education|email|energy|engineer|engineering|enterprises|equipment|estate|events|' + \
    r'exchange|expert|exposed|express|' + \
    r'fail|faith|family|fan|fans|farm|fashion|feedback|film|finance|financial|fish|fishing|fit|fitness|' + \
    r'flights|florist|flower|fly|foo|food|football|forsale|foundation|fun|fund|furniture|futbol|fyi|' + \
    r'gallery|game|games|garden|gay|gdn|gift|gifts|gives|glass|global|gmbh|gold|golf|graphics|gratis|' + \
    r'green|gripe|group|guide|guitars|guru|' + \
    r'hamburg|haus|health|healthcare|help|hiphop|hockey|holdings|holiday|home|homes|horse|hospital|host|' + \
    r'hosting|house|how|' + \
    r'immo|immobilien|inc|industries|info|ink|institute|insure|international|investments|irish|' + \
    r'jetzt|jewelry|juegos|' + \
    r'kitchen|kiwi|koeln|kaufen|' + \
    r'land|law|lawyer|lease|legal|lgbt|life|lifestyle|lighting|limited|limo|link|live|loan|loans|lol|' + \
    r'london|love|ltd|luxury|' + \
    r'maison|management|market|marketing|mba|media|medical|meet|meme|memorial|men|menu|mobi|moda|money|' + \
    r'mortgage|movie|music|' + \
    r'navy|network|new|news|ninja|nyc|' + \
    r'online|ooo|organic|' + \
    r'page|paris|partners|parts|party|pay|pet|pharmacy|photo|photography|photos|physio|pics|pictures|' + \
    r'pizza|place|plumbing|plus|poker|porn|press|pro|productions|promo|properties|property|protection|pub|' + \
    r'qpon|' + \
    r'racing|realty|recipes|red|rehab|reisen|rent|rentals|repair|report|republican|rest|restaurant|review|' + \
    r'reviews|rip|rocks|rodeo|run|' + \
    r'sale|sarl|save|school|schule|science|secure|security|services|sex|sexy|shop|shopping|show|singles|' + \
    r'site|ski|soccer|social|software|solar|solutions|soy|space|spa|sports|spot|srl|store|stream|studio|' + \
    r'study|style|sucks|supplies|supply|support|surf|surgery|systems|' + \
    r'tattoo|tax|taxi|team|tech|technology|tennis|theater|tienda|tips|tires|today|tools|tours|town|toys|' + \
    r'trade|training|tube|' + \
    r'university|uno|' + \
    r'vacations|ventures|vet|viajes|video|villas|vin|vision|vodka|vote|voting|voto|' + \
    r'voyage|' + \
    r'watch|webcam|website|wedding|wien|wiki|win|wine|work|works|world|wtf|' + \
    r'xin|' + \
    r'xyz|' + \
    r'yacht|yoga|' + \
    r'zone|zuerich' + \
    r')' # Ende der TLD-Gruppe
EMAIL_REGEX = re.compile(
    r'(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+' + TLD_LIST + r')', 
    re.IGNORECASE
)
IGNORE_EMAILS_REGEX = re.compile(r'(datenschutz|privacy|@example\.com|@wix\.com|@jimdo\.com|no-reply)', re.IGNORECASE)
IMPRINT_REGEX = re.compile(r'(impressum|imprint|legal-notice|legal|kontakt|contact)', re.IGNORECASE)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
}

# ############################################################################
# --- HELPER FUNKTIONEN ---
# ############################################################################

# Funktion zum Laden der GSheet Credentials aus st.secrets
def get_gspread_credentials():
    """Lädt die GSpread Service Account Credentials aus st.secrets."""
    if not st.secrets:
        st.error("GSheet-Anmeldeinformationen (Secrets) nicht gefunden. Bitte `secrets.toml` einrichten.")
        st.stop()
    
    # Aufbau des Credentials-Objekts aus den Secrets. Diese Struktur muss mit secrets.toml übereinstimmen.
    try:
        creds_info = {
            "type": secrets_data["type"],
            "project_id": secrets_data["project_id"],
            "private_key_id": secrets_data["private_key_id"],
            # WICHTIG: Escaped Newlines (\n) in echte Zeilenumbrüche umwandeln
            "private_key": secrets_data["private_key"].replace('\\n', '\n'),
            "client_email": secrets_data["client_email"],
            "client_id": secrets_data["client_id"],
            "auth_uri": secrets_data["auth_uri"],
            "token_uri": secrets_data["token_uri"], # Hier lag der Fehler: Dieses Feld fehlte vorher
            "auth_provider_x509_cert_url": secrets_data["auth_provider_x509_cert_url"],
            "client_x509_cert_url": secrets_data["client_x509_cert_url"],
            "universe_domain": secrets_data.get("universe_domain", "googleapis.com"),
        }
        return Credentials.from_service_account_info(creds_info, scopes=GSPREAD_SCOPE)
    except KeyError as e:
        st.error(f"Fehler beim Laden der GSheet Secrets: '{e}' fehlt. Überprüfen Sie die Struktur in `secrets.toml`.")
        st.stop()
        
# Ihre originalen Helper-Funktionen (Unverändert)
def normalize_domain(url):
    if not isinstance(url, str): return ""
    url = url.strip().lower()
    if not url.startswith(('http://', 'https://')) and url:
        url = 'http://' + url 
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception:
        return url

def normalize_for_browser(url):
    url = str(url).strip()
    if not url.startswith(('http://', 'https://')):
        return 'https://' + url
    return url

def find_imprint_url_fast(session, base_url):
    try:
        response = session.get(base_url, headers=HEADERS, timeout=5)
        response.raise_for_status() 
    except Exception:
        return None
    soup = BeautifulSoup(response.text, 'html.parser')
    links = soup.find_all('a', href=True)
    for link in links:
        link_text = link.get_text()
        link_href = link['href']
        if IMPRINT_REGEX.search(link_text) or IMPRINT_REGEX.search(link_href):
            absolute_url = urljoin(base_url, link_href)
            return absolute_url
    return None

def find_email_on_page_fast(session, url):
    try:
        response = session.get(url, headers=HEADERS, timeout=5)
        if response.encoding is None:
            response.encoding = 'utf-8'
    except Exception:
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    text_content = soup.get_text(" ").replace(" [at] ", "@").replace(" (at) ", "@").replace("[at]", "@")
    
    emails_found = EMAIL_REGEX.findall(text_content)
    if not emails_found:
        mailtos = soup.select('a[href^=mailto]')
        for m in mailtos:
            href = m.get('href', '')
            if ':' in href:
                emails_found.append(href.split(':')[1].split('?')[0])

    if not emails_found:
        return None
        
    good_emails = []
    for email in set(emails_found): 
        if not IGNORE_EMAILS_REGEX.search(email):
            cleaned = email.strip().rstrip('.')
            good_emails.append(cleaned)
            
    if not good_emails:
        return None
    for email in good_emails:
        if email.startswith(('info@', 'kontakt@', 'hallo@', 'post@', 'mail@', 'office@')):
            return email
    return good_emails[0]

def execute_crawling(website_url):
    email_result = "Keine E-Mail gefunden"
    try:
        with requests.Session() as session:
            imprint_url = find_imprint_url_fast(session, website_url)
            if imprint_url:
                email = find_email_on_page_fast(session, imprint_url)
                if not email:
                    email = find_email_on_page_fast(session, website_url)
            else:
                email = find_email_on_page_fast(session, website_url)
            if email:
                email_result = email
    except Exception as e:
        print(f"Crawl Error: {e}")
    return email_result

def save_entry_and_advance(website_url, anrede, name, final_name_from_input=None):
    
    if final_name_from_input:
        final_name = final_name_from_input
    elif anrede == "Herr" or anrede == "Frau":
        final_name = ""
    else:
        final_name = name 

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with st.spinner(f"Suche E-Mail für {website_url}..."):
        found_email = execute_crawling(website_url)
    
    row_data = [
        website_url,
        found_email,
        anrede,
        final_name, 
        st.session_state.bearbeiter,
        timestamp,
        "", "", "" 
    ]
    
    try:
        st.session_state.ws_main.append_row(row_data)
        display_name = final_name if final_name else "(Firma/Leer)"
        st.toast(f"✅ {anrede} {display_name} gespeichert!")
    except Exception as e:
        st.error(f"Fehler beim Speichern: {e}")

    st.session_state.current_idx += 1
    st.rerun()

# ############################################################################
# --- STREAMLIT UI & SETUP ---
# ############################################################################

def inject_custom_css():
    st.markdown("""
        <style>
            .block-container { padding-top: 1rem; padding-bottom: 10rem; }
            .sticky-footer {
                position: fixed; bottom: 0; left: 0; width: 100%;
                background-color: #f0f2f6; /* Heller Hintergrund für Mobile */
                border-top: 1px solid #ccc;
                padding: 10px; z-index: 9999;
                box-shadow: 0px -2px 10px rgba(0,0,0,0.1);
            }
            iframe { border: 1px solid #ddd; border-radius: 8px; width: 100%; height: 60vh; }
            /* Große Buttons für den Daumen */
            .stButton button { 
                padding: 0.75rem 0.5rem; 
                font-size: 1.1rem; 
                font-weight: bold;
                height: 4em; /* Höhe erhöhen */
            }
        </style>
    """, unsafe_allow_html=True)

def check_password():
    """Zeigt die Passwort-UI an und setzt st.session_state.authenticated auf True bei Erfolg."""
    if st.session_state.get("authenticated", False):
        return True

    st.title("🔐 Login erforderlich")
    with st.form("login"):
        password = st.text_input("Passwort", type="password")
        submitted = st.form_submit_button("Einloggen")

        if submitted:
            if password == HARDCODED_PASSWORD:
                st.session_state.authenticated = True
                st.rerun() # Neu laden, um die Haupt-App zu starten
            else:
                st.error("Falsches Passwort.")
        
        # Stoppt die Ausführung der Haupt-App, solange nicht authentifiziert
        if not st.session_state.get("authenticated", False):
            return False
    
    return st.session_state.authenticated


def main_app_logic():
    """Der Hauptteil der Anwendung, der nur nach erfolgreichem Login läuft."""

    if 'queue' not in st.session_state:
        st.session_state.bearbeiter = ""
        with st.form("login_form"):
            st.title("🚀 Akquise Bot Start")
            st.warning("Hinweis: Es muss eine Datei `input.csv` im Verzeichnis sein.")
            name = st.text_input("Dein Name (Bearbeiter):")
            submitted = st.form_submit_button("Session starten")
            
            if submitted and name:
                st.session_state.bearbeiter = name
                
                if not os.path.exists(FILE_INPUT_DEFAULT):
                    st.error(f"Datei '{FILE_INPUT_DEFAULT}' nicht gefunden! Bitte fügen Sie eine hinzu.")
                    st.stop()
                
                # 1. Google Sheets Initialisierung (mit secrets)
                try:
                    creds = get_gspread_credentials() # Läd Secrets
                    client = gspread.authorize(creds)
                    spreadsheet = client.open_by_url(GSPREAD_SHEET_URL)
                    ws_main = spreadsheet.worksheet(GSPREAD_SHEET_NAME_MAIN)
                    ws_rejected = spreadsheet.worksheet(GSPREAD_SHEET_NAME_REJECTED)
                    existing_main = set(normalize_domain(x) for x in ws_main.col_values(1)[1:])
                    existing_rejected = set(normalize_domain(x) for x in ws_rejected.col_values(1)[1:])
                    all_existing = existing_main.union(existing_rejected)
                except Exception as e:
                    st.error(f"GSheet Fehler: {e}")
                    st.stop()

                # 2. Input-CSV laden und Duplikate filtern
                df_input = pd.read_csv(FILE_INPUT_DEFAULT)
                df_input.columns = [c.strip().strip('"') for c in df_input.columns]
                queue = []
                for index, row in df_input.iterrows():
                    url = row.get('website', '')
                    if normalize_domain(url) not in all_existing and normalize_domain(url) != "":
                        queue.append(url)
                
                # 3. Session State setzen
                st.session_state.queue = queue
                st.session_state.current_idx = 0
                st.session_state.ws_main = ws_main
                st.session_state.ws_rejected = ws_rejected
                st.rerun()
            else:
                st.stop() # Stoppt hier, bis das Formular ausgefüllt ist

    if st.session_state.current_idx >= len(st.session_state.queue):
        st.success("🎉 Alle Websites aus input.csv sind bearbeitet!")
        if st.button("Cache leeren / Neustart"):
            st.session_state.clear()
            st.rerun()
        st.stop()

    current_url_raw = st.session_state.queue[st.session_state.current_idx]
    website_url = normalize_for_browser(current_url_raw)
    
    prog = (st.session_state.current_idx) / len(st.session_state.queue)
    st.progress(prog)
    st.caption(f"Website {st.session_state.current_idx + 1} von {len(st.session_state.queue)} | Bearbeiter: {st.session_state.bearbeiter}")

    col_link, col_info = st.columns([1, 3])
    with col_link:
        st.link_button("🌍 Öffnen", website_url)
    with col_info:
        st.markdown(f"**{website_url}**")
        
    try:
        st.components.v1.iframe(website_url, height=600, scrolling=True)
    except:
        st.warning("Vorschau blockiert - bitte Link nutzen.")

    # --- STICKY FOOTER (Optimiertes Button-Layout) ---
    st.markdown('<div class="sticky-footer">', unsafe_allow_html=True)
    
    c_herr_frau, c_firma, c_reject = st.columns([1, 1, 1])
    
    with c_herr_frau:
        with st.popover("🙋 Kontakt gefunden", use_container_width=True):
            st.markdown("##### Ansprechpartner eintragen:")
            
            input_name_dialog = st.text_input("Name der Person", key="pop_name")

            if st.button("👨 Speichern als Herr", use_container_width=True):
                 if input_name_dialog:
                     save_entry_and_advance(website_url, "Herr", "", input_name_dialog)
                 else:
                     st.warning("Bitte Namen eingeben.")
                     
            if st.button("👩 Speichern als Frau", use_container_width=True):
                 if input_name_dialog:
                     save_entry_and_advance(website_url, "Frau", "", input_name_dialog)
                 else:
                     st.warning("Bitte Namen eingeben.")
                     
    with c_firma:
        if st.button("✅ Aktzeptieren", type="primary", use_container_width=True):
            save_entry_and_advance(website_url, "", "", "")

    with c_reject:
        if st.button("❌ Ablehnen", type="secondary", use_container_width=True):
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                st.session_state.ws_rejected.append_row([website_url, timestamp])
                st.toast(f"❌ {website_url} abgelehnt")
            except Exception as e:
                st.error(f"Fehler beim Speichern: {e}")
            
            st.session_state.current_idx += 1
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


def main():
    st.set_page_config(page_title="Akquise Bot", layout="wide", initial_sidebar_state="collapsed")
    inject_custom_css()
    
    # 1. Passwortprüfung
    if check_password():
        # 2. Hauptlogik nur, wenn erfolgreich authentifiziert
        main_app_logic()


if __name__ == "__main__":
    main()
