---
name: logiphys-ci
description: "Logiphys Corporate Identity Branding für Dokumente (DOCX und PDF). Verwende diesen Skill IMMER wenn ein DOCX-Dokument, PDF, Bericht, Brief, Angebot, Protokoll oder sonstiges Geschäftsdokument für Logiphys oder im Namen von Logiphys erstellt wird. Auch verwenden wenn der Benutzer 'mit CI', 'mit Logo', 'mit Branding', 'Logiphys-Layout' oder 'Firmen-Design' erwähnt. Dieser Skill ergänzt den docx- und pdf-Skill — lies IMMER zuerst den jeweiligen Format-Skill und dann diesen hier für das Branding."
---

# Logiphys CI — Corporate Identity Branding

Dieser Skill sorgt dafür, dass alle Geschäftsdokumente von Logiphys einheitlich aussehen: Logo im Header, Kontaktdaten im Footer, und die Firmenfarben durchgängig.

## Wann diesen Skill verwenden

- Bei JEDEM DOCX- oder PDF-Dokument das für/von Logiphys erstellt wird
- Bei Berichten, Angeboten, Protokollen, Briefen, Diagnoseberichten
- Wenn der Benutzer „mit CI", „mit Logo", „Logiphys-Branding" o.ä. erwähnt
- Auch wenn es nicht explizit erwähnt wird — wenn das Dokument geschäftlich für Logiphys ist, immer CI anwenden

## CI-Konfiguration laden

Lies zu Beginn die CI-Konfigurationsdatei:
```
/Users/zeisler/Documents/Claude/Memory/ci.md
```

## Logo laden — WICHTIG

Das Logo liegt in zwei Versionen vor. **Für Dokument-Header immer die HDR-Version verwenden** (200?45px, ~6KB) — passt in einen einzigen osascript-Aufruf.

### Dateien
- **PNG Original** (800?181px, 33KB): `/Users/zeisler/Documents/Claude/Memory/assets/logiphys_logo.png`
- **PNG Header** (200?45px, ~6KB ?): `/Users/zeisler/Documents/Claude/Memory/assets/logiphys_logo_hdr.png`
- **Base64 Header** (~9.8KB, ein Aufruf reicht): `/Users/zeisler/Documents/Claude/Memory/assets/logiphys_logo_hdr.b64`
- **SVG** (Vektorgrafik): `/Users/zeisler/Documents/Claude/Memory/assets/logiphys_logo.svg`

### Logo in die Sandbox übertragen

```
# Via osascript (ein Aufruf reicht für ~9.8KB):
do shell script "python3 -c \"import base64; data=open('/Users/zeisler/Documents/Claude/Memory/assets/logiphys_logo_hdr.png','rb').read(); print(base64.b64encode(data).decode())\""

# Ergebnis in der Sandbox per Python dekodieren:
import base64
with open('/sessions/loving-awesome-archimedes/logiphys_logo.png', 'wb') as f:
    f.write(base64.b64decode(b64_string_from_above))
```

### Verifikation

```bash
python3 -c "d=open('/sessions/loving-awesome-archimedes/logiphys_logo.png','rb').read(4); print('OK' if d==b'\x89PNG' else f'FEHLER: {d}')"
# Erwartete Ausgabe: OK — Dateigröße ~6KB
```

## Farben (Hex)

| Name        | Hex       | Verwendung                          |
|-------------|-----------|--------------------------------------|
| Logo-Blau   | `#2478B6` | Akzente, Gradient                    |
| Logo-Teal   | `#00ACA9` | Akzente, Gradient                    |
| Primär-Blau | `#205493` | Überschriften, Header, Footer-Linie  |
| Text-Dunkel | `#3C3C3B` | Fließtext                            |
| Weiß        | `#FFFFFF` | Hintergrund, helle Flächen           |
| Hellgrau    | `#F5F5F5` | Hintergrund Alternativ               |

## Schriften

- **Überschriften**: Titillium Web SemiBold (600) — Fallback: Calibri, Arial
- **Fließtext**: Titillium Web Regular (400) — Fallback: Calibri, Arial

---

## DOCX-Layout Vorgaben

### Header
1. Logo linksbündig einfügen (200?45px — HDR-Version direkt verwenden, kein Resize nötig)
2. Dünne horizontale Linie darunter in Primär-Blau (#205493), Stärke 1pt

```javascript
const logoData = fs.readFileSync('/sessions/loving-awesome-archimedes/logiphys_logo.png');

new Header({
  children: [
    new Paragraph({
      children: [
        new ImageRun({
          data: logoData,
          transformation: { width: 200, height: 45 },
          type: 'png',
          altText: { title: 'Logiphys Logo', description: 'Logiphys Datensysteme GmbH', name: 'logo' },
        }),
      ],
    }),
    new Paragraph({
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: '205493' } },
      spacing: { after: 200 },
    }),
  ],
});
```

### Footer
1. Trennlinie in Primär-Blau (#205493), Stärke 1pt
2. Zeile 1: **Logiphys Datensysteme GmbH** | Kuhnbergstraße 16 | 73037 Göppingen
3. Zeile 2: www.logiphys.de | info@logiphys.de
4. Seitenzahl rechtsbündig
5. Schriftgröße: 8pt, Farbe: #3C3C3B

```javascript
new Footer({
  children: [
    new Paragraph({
      border: { top: { style: BorderStyle.SINGLE, size: 6, color: '205493' } },
      spacing: { before: 200 },
      children: [
        new TextRun({ text: 'Logiphys Datensysteme GmbH', bold: true, size: 16, color: '3C3C3B', font: 'Calibri' }),
        new TextRun({ text: '  |  Kuhnbergstraße 16  |  73037 Göppingen', size: 16, color: '3C3C3B', font: 'Calibri' }),
      ],
    }),
    new Paragraph({
      children: [
        new TextRun({ text: 'www.logiphys.de  |  info@logiphys.de', size: 16, color: '3C3C3B', font: 'Calibri' }),
      ],
    }),
    new Paragraph({
      alignment: AlignmentType.RIGHT,
      children: [
        new TextRun({ text: 'Seite ', size: 16, color: '3C3C3B', font: 'Calibri' }),
        new TextRun({ children: [PageNumber.CURRENT], size: 16, color: '3C3C3B', font: 'Calibri' }),
        new TextRun({ text: ' / ', size: 16, color: '3C3C3B', font: 'Calibri' }),
        new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: '3C3C3B', font: 'Calibri' }),
      ],
    }),
  ],
});
```

### Überschriften-Formatierung

```javascript
{ id: 'Heading1', run: { size: 32, bold: true, color: '205493', font: 'Calibri' }, paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0 } }
{ id: 'Heading2', run: { size: 26, bold: true, color: '205493', font: 'Calibri' }, paragraph: { spacing: { before: 240, after: 100 }, outlineLevel: 1 } }
{ id: 'Heading3', run: { size: 22, bold: true, color: '2478B6', font: 'Calibri' }, paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2 } }
```

### Seitenränder

```javascript
page: {
  size: { width: 11906, height: 16838 },  // A4
  margin: { top: convertMillimetersToTwip(25), bottom: convertMillimetersToTwip(20), left: convertMillimetersToTwip(25), right: convertMillimetersToTwip(20) },
}
```

---

## PDF-Layout Vorgaben

Für PDFs mit Logiphys-CI verwende Python mit `reportlab`.

```python
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Image

PRIMARY_BLUE = HexColor('#205493')
LOGO_BLUE    = HexColor('#2478B6')
TEXT_DARK    = HexColor('#3C3C3B')
LIGHT_GRAY   = HexColor('#F5F5F5')

logo = Image('/sessions/loving-awesome-archimedes/logiphys_logo.png', width=70*mm, height=15.85*mm)

doc = SimpleDocTemplate(output_path, pagesize=A4,
    leftMargin=25*mm, rightMargin=20*mm, topMargin=25*mm, bottomMargin=20*mm)
```

---

## Checkliste vor Fertigstellung

- [ ] Logo geladen und validiert (PNG-Header `\x89PNG`, ~6KB)
- [ ] Header: Logo links, Trennlinie in #205493
- [ ] Footer: Firmenname, Adresse, Web, Mail, Seitenzahl
- [ ] Überschriften in #205493, Fließtext in #3C3C3B
- [ ] Seitenränder 25/20/25/20 mm, Seitengröße A4

<!-- Updated 2026-04-02 — HDR-Logo (200?45px, ~6KB) löst Base64-Transferproblem dauerhaft. logiphys_logo_hdr.png + .b64 in assets. -->
