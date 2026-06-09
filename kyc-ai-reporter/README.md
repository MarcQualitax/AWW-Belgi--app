# KYC AI Reporter België

FastAPI-startproject dat enkel een Belgisch ondernemingsnummer vraagt en daarna een auditbaar AWW/KYC/MKS-rapport opbouwt uit toegestane bronnen.

## Belangrijk
Dit project is een technische basis, geen juridisch advies en geen vervanging voor menselijke compliance-review. Gebruik enkel officiële API's, contractuele databronnen of bronnen waarvoor je toestemming/rechtsgrond hebt. Vermijd ongeoorloofde scraping van Facebook, Google, Graydon/Credendo/Companyweb of andere betaalde bronnen.

## Bronnen/connectoren
- KBO Public Search/Webservice: officiële bedrijfsgegevens
- NBB Balanscentrale: jaarrekeningen
- Belgisch Staatsblad: publicaties en mandaten/statutenwijzigingen
- Internet/Google Custom Search: reputatie, adverse media, websites
- Graydon/Craydon of andere commerciële bron: alleen via geldige API-licentie
- Facebook/social media: alleen via toegestane API's en GDPR-rechtsgrond

## Snel starten
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open daarna: http://127.0.0.1:8000/docs

## Endpoint
`POST /reports`

```json
{
  "enterprise_number": "0123.456.789",
  "purpose": "onboarding klant",
  "language": "nl"
}
```

Antwoord bevat JSON met risicoscore, bevindingen, ontbrekende gegevens, bronverwijzingen en een rapporttekst. Later kan je PDF-output activeren via `/reports/{id}/pdf`.
