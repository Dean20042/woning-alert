import os
import re
import json
import hashlib
import smtplib
from email.message import EmailMessage

from playwright.sync_api import sync_playwright

URL = "https://www.woninghuren.nl/aanbod/te-huur"
MAX_HUUR = 800
MIN_KAMERS = 3  # 2 slaapkamers betekent meestal minimaal 3 kamers

EMAIL_TO = "deanhulman@gmail.com"
EMAIL_FROM = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

STATE_FILE = "bekende_woningen.json"

# Alleen links die naar een echte advertentie verwijzen, geen menu/footer-links.
DETAIL_PATH = "/aanbod/te-huur/details/"


def get_woningen():
    """
    Opent de pagina in een echte (headless) browser zodat JavaScript-inhoud
    (zoals huurprijs en aantal kamers) ook echt geladen wordt, en haalt
    daarna alle advertentielinks met bijbehorende tekst op.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            user_agent="Mozilla/5.0 (compatible; WoningAlert/1.0)"
        )
        page.goto(URL, wait_until="networkidle", timeout=60000)
        # Extra marge voor eventuele vertraagde (lazy-loaded) inhoud
        page.wait_for_timeout(3000)

        data = page.evaluate(
            """
            (detailPath) => {
                const links = Array.from(document.querySelectorAll('a[href*="' + detailPath + '"]'));
                const seen = new Set();
                const result = [];
                for (const link of links) {
                    const href = link.href;
                    if (seen.has(href)) continue;
                    seen.add(href);

                    // Klim een paar niveaus omhoog in de HTML, zodat we ook
                    // de prijs/kamers-tekst rond de link meepakken.
                    let node = link;
                    for (let i = 0; i < 3 && node.parentElement; i++) {
                        node = node.parentElement;
                    }

                    result.push({
                        url: href,
                        text: node.innerText.replace(/\\s+/g, ' ').trim()
                    });
                }
                return result;
            }
            """,
            DETAIL_PATH,
        )
        browser.close()

    return data


def parse_prijs(text):
    """Haalt het eerste bedrag na een € teken uit de tekst, als getal."""
    match = re.search(r"€\s*([\d.,]+)", text)
    if not match:
        return None
    getal = match.group(1).replace(".", "").replace(",", ".")
    try:
        return float(getal)
    except ValueError:
        return None


def parse_kamers(text):
    """Haalt het aantal kamers/slaapkamers uit de tekst, als getal."""
    match = re.search(r"(\d+)\s*(slaapkamer|kamer)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def voldoet_aan_criteria(woning):
    """
    True als de woning past binnen MAX_HUUR en MIN_KAMERS.
    Als prijs/kamers niet uit de tekst te halen zijn, laten we 'm er
    (voor de zekerheid) toch doorheen, zodat je niks mist.
    """
    prijs = parse_prijs(woning["text"])
    kamers = parse_kamers(woning["text"])
    woning["prijs"] = prijs
    woning["kamers"] = kamers

    if prijs is not None and prijs > MAX_HUUR:
        return False
    if kamers is not None and kamers < MIN_KAMERS:
        return False
    return True


def woning_id(woning):
    return hashlib.sha256(woning["url"].encode("utf-8")).hexdigest()


def load_known():
    if not os.path.exists(STATE_FILE):
        return set()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_known(ids):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, indent=2)


def send_email(nieuwe_woningen):
    msg = EmailMessage()
    msg["Subject"] = f"🏠 {len(nieuwe_woningen)} nieuwe woning(en) op WoningHuren.nl"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    body = [
        "Nieuwe woning(en) gevonden op WoningHuren.nl:",
        "",
    ]
    for woning in nieuwe_woningen:
        body.append(f"🏠 {woning['text'][:250]}")
        body.append(f"🔗 {woning['url']}")
        body.append("")
    body.append(
        "Controleer altijd op WoningHuren.nl of de woning "
        "voor jullie passend is."
    )
    msg.set_content("\n".join(body))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_FROM, EMAIL_PASSWORD)
        smtp.send_message(msg)


def main():
    known = load_known()
    woningen = get_woningen()

    nieuwe = []
    for woning in woningen:
        wid = woning_id(woning)
        if wid in known:
            continue
        known.add(wid)
        if voldoet_aan_criteria(woning):
            nieuwe.append(woning)

    save_known(known)

    if nieuwe:
        send_email(nieuwe)
        print(f"{len(nieuwe)} nieuwe passende woningen gemeld.")
    else:
        print("Geen nieuwe passende woningen.")


if __name__ == "__main__":
    main()
