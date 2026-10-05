# wheel-owners

**Installationspfade eines lokalen Python-Wheel-Satzes vor der Installation auf Konflikte prüfen.**

[English](../README.md) · [简体中文](README.zh-CN.md) · [Русский](README.ru.md) · Deutsch

`wheel-owners` berechnet die Zielpfade ausdrücklich angegebener Wheels anhand
eines vorgegebenen Installationslayouts. Es meldet mehrfach beanspruchte Dateien
und Konflikte zwischen Dateien und Verzeichnissen. Dafür nutzt es die festgelegte
Version `installer==0.7.0` mit einem Zieladapter, der die Ergebnisse lediglich
aufzeichnet. Die geprüften Pakete werden nicht installiert; ihr Code wird weder
importiert noch ausgeführt.

Ein erfolgreiches Ergebnis bedeutet nur, dass die übergebenen Dateien im
unterstützten Modell keine Eigentumskonflikte erzeugen. Es garantiert weder
passende Abhängigkeiten noch korrekte Imports, ABI-Kompatibilität oder Sicherheit.

## Schnellstart

Voraussetzung ist Python 3.10 oder neuer auf einem POSIX-System. Im Quellverzeichnis:

```sh
python -m pip install .
wheel-owners --layout examples/posix-layout.json a.whl b.whl
```

Ersetzen Sie `a.whl` und `b.whl` durch echte lokale Wheel-Dateinamen. Diese
Anleitung setzt keine Veröffentlichung auf PyPI voraus. Beim Installieren des
Werkzeugs können Abhängigkeiten heruntergeladen werden; der Prüfbefehl selbst
verwendet kein Netzwerk.

Geben Sie alle zu prüfenden Artefakte einschließlich der bereits ausgewählten
Abhängigkeiten ausdrücklich an. Das Werkzeug löst keine Abhängigkeiten auf,
lädt keine Pakete herunter, durchsucht keine Verzeichnisse rekursiv und untersucht
keine bestehende Umgebung. Pro normalisiertem Distributionsnamen ist nur ein
Artefakt zulässig. Wählen Sie Version und Plattformvariante vorher aus.

## Installationslayout

`--layout` erwartet striktes JSON. Unterstützt wird ausschließlich das Profil
`posix-case-sensitive-v1`:

```json
{
  "profile": "posix-case-sensitive-v1",
  "interpreter": "/venv/bin/python",
  "scheme": {
    "purelib": "/venv/lib/python3.12/site-packages",
    "platlib": "/venv/lib/python3.12/site-packages",
    "scripts": "/venv/bin",
    "headers": "/venv/include",
    "data": "/venv"
  }
}
```

Alle fünf Schemapfade sind erforderlich. Sämtliche Pfade müssen absolute,
normalisierte POSIX-Pfade sein. Sie sind Modelleingaben: Die Verzeichnisse
werden weder angelegt noch untersucht. `interpreter` wird zur Skripterzeugung
verwendet, aber nicht ausgeführt. Passen Sie das Beispiel an die geplante
Installation an.

Pfade werden exakt nach Unicode-Codepunkten verglichen. Unicode-Normalisierung,
die Behandlung von Groß- und Kleinschreibung unter Windows oder macOS sowie
symbolische Links werden nicht nachgebildet. Das Profil bildet kein reales
Dateisystem vollständig ab.

## Konfliktregeln

- Mehrere Besitzer beanspruchen denselben Zielpfad einer Datei, auch bei
  identischem Inhalt.
- Ein Pfad müsste zugleich Datei und übergeordnetes Verzeichnis sein.
- Erzeugte console/GUI-Entry-Point-Skripte, enthaltene Skripte oder andere Dateien
  beanspruchen denselben Zielpfad.
- Unterschiedliche Schemabereiche führen zum gleichen Zielpfad.

Unterstützte Zuordnungen aus dem Wheel-Wurzelverzeichnis und aus `.data` werden
berücksichtigt. Gemeinsam genutzte Verzeichnisse allein sind erlaubt.
Namespace-Pakete mit getrennten Dateien können daher bestehen; ihre korrekte
Importauflösung wird damit nicht nachgewiesen.

## Ausgabe und Rückgabecodes

Die Ausgabe ist deterministisches JSON mit `schema_version: 1`.

| Code | Bedeutung |
| --- | --- |
| `0` | Keine Eigentumskonflikte im unterstützten Modell gefunden |
| `1` | Eigentumskonflikte gefunden |
| `2` | Ungültige Eingabe oder nicht unterstützter Fall; kein bestandener Test |

Die deterministische Ausgabe gilt bei gleichen Eingaben, gleichem Layout und
gleichen Werkzeug- und Abhängigkeitsversionen. Fehlerhafte Wheels oder Pfade,
nicht unterstützte Versionen oder Transformationen und mehrfach angegebene
normalisierte Distributionsnamen werden abgelehnt. Ein Prozessfehler oder ein
fehlender Bericht darf nicht als Erfolg gelten.

Bytecode-Erzeugung, die Ausführung von `.pth`, Import-Hooks und Editable-Installationen
werden nicht modelliert. Die vollständigen Grenzen stehen in [limits.md](limits.md).

## Verwandte Arbeiten und Entwicklung

Das Projekt erhebt keinen Anspruch darauf, Konflikterkennung erfunden zu haben.
Der [Vergleich mit Primärquellen](comparison.md) nennt pip #4625, pip PR #14249,
`pip check`, `check-wheel-contents`, ModuleGuard und SPIRA Trust.
Der Upstream-Status wurde am 2026-10-05 geprüft und muss vor einer Veröffentlichung
erneut geprüft werden.

```sh
python -m pip install -e '.[test]'
python -m pytest
python -m build
```

Für den Build muss `build` in der Entwicklungsumgebung installiert sein.
Siehe [Mitwirken](../CONTRIBUTING.md), [Sicherheit](../SECURITY.md)
und [MIT-Lizenz](../LICENSE). Der ausführliche Vertrag steht im
[englischen README](../README.md).
