#!/usr/bin/env python3
"""Calendario Movistar Estudiantes (masc, Primera FEB 26/27) -> partidos.json + estudiantes.ics.

Fuente: FEB competiciones.feb.es/estadisticas/Calendario.aspx
  - celda 'resultado' con marcador  => partido jugado
  - celda 'fecha' con DIA dd/mm/aaaa hh:mm => pendiente (hora Madrid)
Solo stdlib. UIDs estables por jornada para que Google actualice sin duplicar.
"""
import json, re, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

BASE = Path(__file__).resolve().parent
JSON_PATH = BASE / "datos" / "partidos.json"
ICS_PATH = BASE / "estudiantes.ics"
FEB_URL = "https://competiciones.feb.es/estadisticas/Calendario.aspx"
ESTU_ID = "1010493"
MADRID = ZoneInfo("Europe/Madrid")

COMPETICION = "Primera FEB 26/27"
CASA_PABELLON = "Movistar Arena, Madrid"


def fetch() -> str:
    req = urllib.request.Request(FEB_URL, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")


def title_case(s: str) -> str:
    s = s.strip().lower()
    out = []
    for w in s.split():
        if w in ("cb", "cd", "ad", "sd", "xb"):
            out.append(w.upper())
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def parse(html: str) -> list[dict]:
    blocks = re.findall(r"Jornada\s+(\d+)\s+(\d{2}/\d{2}/\d{4})(.*?)(?=Jornada\s+\d+\s+\d{2}/|$)", html, re.S)
    partidos = []
    for jnum, jdate, body in blocks:
        for r in re.findall(r"<tr>(.*?)</tr>", body, re.S):
            if ESTU_ID not in r:
                continue
            pid = re.search(r"Partido\.aspx\?p=(\d+)", r).group(1)
            names = re.findall(r"Equipo\.aspx\?i=\d+\">([^<]+)</a>", r)
            m = re.search(r'<td class="(resultado|fecha)">\s*<a[^>]*>(.*?)</a>', r, re.S)
            cell = re.sub(r"\s+", " ", m.group(2)).strip()
            pos_estu = r.find(ESTU_ID)
            pos_mid = r.find('class="resultado"') if 'class="resultado"' in r else r.find('class="fecha"')
            casa = pos_estu < pos_mid
            rival_raw = names[1] if casa else names[0]
            score = re.match(r"(\d+)\s*-\s*(\d+)", cell)
            p = {
                "jornada": int(jnum),
                "fecha_jornada": jdate,
                "uid": f"estu-2627-j{int(jnum):02d}@estudiantes-calendario",
                "casa": casa,
                "rival": title_case(rival_raw),
                "feb_partido_id": pid,
                "acta": f"https://baloncestoenvivo.feb.es/Partido.aspx?p={pid}",
                "estado": "jugado" if score else "pendiente",
            }
            if score:
                gl, gv = int(score.group(1)), int(score.group(2))
                p["resultado_local"], p["resultado_visitante"] = gl, gv
                pe, pr = (gl, gv) if casa else (gv, gl)
                p["resultado_estu"], p["resultado_rival"] = pe, pr
                p["victoria"] = pe > pr
            else:
                dm = re.search(r"(\d{2})/(\d{2})/(\d{4})<br/>(\d{2}):(\d{2})", cell)
                if not dm:
                    raise ValueError(f"fecha no parseable J{jnum}: {cell}")
                d, mo, y, h, mi = map(int, dm.groups())
                p["inicio_madrid"] = f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:00"
            partidos.append(p)
    partidos.sort(key=lambda p: p["jornada"])
    return partidos


def resumen(p: dict) -> str:
    tag = f"J{p['jornada']}"
    if p["estado"] == "jugado":
        marca = "✅" if p["victoria"] else "❌"
        return f"🏀 Estu {p['resultado_estu']}-{p['resultado_rival']} {p['rival']} {marca} ({tag})"
    lugar = "en casa" if p["casa"] else f"en {p['rival']}"
    return f"🏀 Estu vs {p['rival']} {lugar} ({tag})"


def descripcion(p: dict) -> str:
    lineas = [f"{COMPETICION} · Jornada {p['jornada']}",
              ("Estu en casa" if p["casa"] else "Estu fuera") + f" vs {p['rival']}"]
    if p["estado"] == "jugado":
        lineas.append(f"Resultado: Estu {p['resultado_estu']}-{p['resultado_rival']} "
                      + ("victoria ✅" if p["victoria"] else "derrota ❌"))
    else:
        dt = datetime.fromisoformat(p["inicio_madrid"])
        lineas.append(f"Inicio: {dt.strftime('%d/%m/%Y %H:%M')} (Madrid)")
    lineas.append(f"Acta FEB: {p['acta']}")
    return "\\n".join(lineas)


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(partidos: list[dict]) -> str:
    now = datetime.now(MADRID).astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//estudiantes-calendario//ES",
         "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Movistar Estudiantes 26/27",
         "X-WR-TIMEZONE:Europe/Madrid"]
    for p in partidos:
        if p["estado"] == "jugado" and "inicio_madrid" in p:
            start = datetime.fromisoformat(p["inicio_madrid"]).replace(tzinfo=MADRID)
        elif p["estado"] == "jugado":
            d, mo, y = map(int, p["fecha_jornada"].split("/"))
            start = datetime(y, mo, d, 12, 0, tzinfo=MADRID)
        else:
            start = datetime.fromisoformat(p["inicio_madrid"]).replace(tzinfo=MADRID)
        end = start + timedelta(hours=2)
        su, eu = start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))
        L += ["BEGIN:VEVENT",
              f"UID:{p['uid']}",
              f"DTSTAMP:{now}",
              f"DTSTART:{su.strftime('%Y%m%dT%H%M%SZ')}",
              f"DTEND:{eu.strftime('%Y%m%dT%H%M%SZ')}",
              f"SUMMARY:{esc(resumen(p))}",
              f"DESCRIPTION:{esc(descripcion(p))}",
              f"URL:{p['acta']}"]
        if p["casa"]:
            L.append(f"LOCATION:{esc(CASA_PABELLON)}")
        L += ["TRANSP:TRANSPARENT", "STATUS:CONFIRMED", "SEQUENCE:0", "END:VEVENT"]
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"


def main() -> None:
    partidos = parse(fetch())
    assert len(partidos) == 34, f"esperaba 34 jornadas, hay {len(partidos)}"
    # conservar inicio_madrid de pendientes que pasan a jugados (para fecha real del evento)
    if JSON_PATH.exists():
        prev = {p["uid"]: p for p in json.loads(JSON_PATH.read_text())}
        for p in partidos:
            old = prev.get(p["uid"])
            if old and p["estado"] == "jugado" and "inicio_madrid" in old:
                p["inicio_madrid"] = old["inicio_madrid"]
                if p["casa"]:
                    pass
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(partidos, ensure_ascii=False, indent=2) + "\n")
    ICS_PATH.write_text(to_ics(partidos))
    jug = sum(1 for p in partidos if p["estado"] == "jugado")
    print(f"jornadas={len(partidos)} jugados={jug} pendientes={len(partidos)-jug}")
    print(f"json={JSON_PATH} ics={ICS_PATH}")


if __name__ == "__main__":
    main()
