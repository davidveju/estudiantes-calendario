#!/usr/bin/env python3
"""Calendario Movistar Estudiantes (masc, 26/27) -> partidos.json + estudiantes.ics.

Fuentes FEB:
  - Liga (Primera FEB): competiciones.feb.es/estadisticas/Calendario.aspx
      celda 'resultado' con marcador  => jugado
      celda 'fecha' con DIA dd/mm/aaaa hh:mm => pendiente (hora Madrid)
  - Copa (eliminatorias a partido unico): www.feb.es/competiciones/resultados/copaespaa/73/2026
      tabla Equipos | Resultado (*-* = pendiente) | Fecha | Hora
Solo stdlib. UIDs estables por jornada/ronda para que Google actualice sin duplicar.
Playoffs (13/05-06/06/2027): cuando la FEB publique su pagina, anadir URL + parse_*
siguiendo el patron de la copa.
"""
import json, re, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # repo root (script vive en scripts/)
JSON_PATH = BASE / "datos" / "partidos.json"
SEDES_PATH = BASE / "datos" / "sedes.json"
ICS_PATH = BASE / "estudiantes.ics"
LIGA_URL = "https://competiciones.feb.es/estadisticas/Calendario.aspx"
COPA_URL = "https://www.feb.es/competiciones/resultados/copaespaa/73/2026"
ESTU_ID = "1010493"
MADRID = ZoneInfo("Europe/Madrid")

LIGA_NOMBRE = "Primera FEB 26/27"
COPA_NOMBRE = "Copa España 26/27"
RONDAS_COPA = {1: "1/16", 2: "1/8", 3: "1/4", 4: "Semifinal", 5: "Final"}
CASA_PABELLON = "Movistar Arena, Madrid"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")


def fetch_sede(pid: str) -> dict:
    """Pabellón + dirección desde la ficha del partido (verificado J1/J4/J5/J34)."""
    import time
    req = urllib.request.Request(
        f"https://baloncestoenvivo.feb.es/Partido.aspx?p={pid}",
        headers={"User-Agent": "Mozilla/5.0"})
    h = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    time.sleep(1)
    m = re.search(r'<div class="pista">(.*?)</div>\s*</div>', h, re.S)
    if not m:
        return {}
    pab = re.search(r'class="txt pabellon">(.*?)</span>', m.group(1))
    drc = re.search(r'class="txt direccion">(.*?)</span>', m.group(1))
    return {"pabellon": title_case(pab.group(1)) if pab else "",
            "direccion": drc.group(1).strip() if drc else ""}


def title_case(s: str) -> str:
    minus = {"de", "del", "la", "el", "los", "las", "en", "y", "a", "al"}
    siglas = {"cb", "cd", "ad", "sd", "xb", "alb", "bca"}
    out = []
    for i, w in enumerate(s.strip().lower().split()):
        if w in siglas:
            out.append(w.upper())
        elif w in minus and i > 0:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def parse_liga(html: str) -> list[dict]:
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
                "competicion": "liga",
                "competicion_nombre": LIGA_NOMBRE,
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
                    raise ValueError(f"liga: fecha no parseable J{jnum}: {cell}")
                d, mo, y, h, mi = map(int, dm.groups())
                p["inicio_madrid"] = f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:00"
            partidos.append(p)
    partidos.sort(key=lambda p: p["jornada"])
    return partidos


def parse_copa(html: str) -> list[dict]:
    """Copa España: eliminatorias a partido unico; fecha+hora en columnas propias."""
    opciones = set(re.findall(r"<option[^>]*>\s*Jornada\s+(\d+)", html))
    if len(opciones) > 1:
        raise ValueError(f"copa: hay {len(opciones)} jornadas publicadas, el parser solo lee la actual")
    if not opciones:
        raise ValueError("copa: no se encontro ninguna jornada (cambio la pagina FEB)")
    jnum = int(opciones.pop())
    ronda = RONDAS_COPA.get(jnum, f"J{jnum}")
    partidos = []
    for r in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        if ESTU_ID not in r or "Equipo.aspx" not in r:
            continue
        eq = re.search(r"Equipo\.aspx\?i=(\d+)\"[^>]*>([^<]+)</a>\s*-\s*"
                       r"<a[^>]*Equipo\.aspx\?i=(\d+)\"[^>]*>([^<]+)</a>", r)
        rs = re.search(r"Partido\.aspx\?p=(\d+)\"[^>]*>(.*?)</a>", r, re.S)
        fh = re.search(r"<td>\s*(\d{2}/\d{2}/\d{4})\s*</td>\s*<td>\s*(\d{2}:\d{2})?", r)
        if not (eq and rs and fh):
            raise ValueError(f"copa: fila del Estu no parseable: {re.sub(r'\s+', ' ', r)[:200]}")
        id_loc, nom_loc, id_vis, nom_vis = eq.groups()
        pid, res_txt = rs.group(1), re.sub(r"\s+", " ", rs.group(2)).strip()
        fecha, hora = fh.groups()
        casa = (id_loc == ESTU_ID)
        score = re.match(r"(\d+)\s*-\s*(\d+)", res_txt)
        p = {
            "jornada": jnum,
            "ronda": ronda,
            "fecha_jornada": fecha,
            "uid": f"estu-2627-copa-j{jnum:02d}@estudiantes-calendario",
            "competicion": "copa",
            "competicion_nombre": COPA_NOMBRE,
            "casa": casa,
            "rival": title_case(nom_vis if casa else nom_loc),
            "feb_partido_id": pid,
            "acta": f"https://www.feb.es/competiciones/Partido.aspx?p={pid}",
            "estado": "jugado" if score else "pendiente",
        }
        d, mo, y = map(int, fecha.split("/"))
        hh, mm = map(int, (hora or "12:00").split(":"))
        p["inicio_madrid"] = f"{y:04d}-{mo:02d}-{d:02d}T{hh:02d}:{mm:02d}:00"
        if res_txt in ("*-*", "-", ""):
            pass
        elif score:
            gl, gv = int(score.group(1)), int(score.group(2))
            p["resultado_local"], p["resultado_visitante"] = gl, gv
            pe, pr = (gl, gv) if casa else (gv, gl)
            p["resultado_estu"], p["resultado_rival"] = pe, pr
            p["victoria"] = pe > pr
        else:
            raise ValueError(f"copa: resultado no parseable: {res_txt!r}")
        partidos.append(p)
    return partidos


def etiqueta(p: dict) -> str:
    return f"Copa {p['ronda']}" if p["competicion"] == "copa" else f"J{p['jornada']}"


def resumen(p: dict) -> str:
    emoji = "🏆" if p["competicion"] == "copa" else "🏀"
    tag = etiqueta(p)
    local = "Estu" if p["casa"] else p["rival"]
    visitante = p["rival"] if p["casa"] else "Estu"
    if p["estado"] == "jugado":
        marca = "✅" if p["victoria"] else "❌"
        gl, gv = p["resultado_local"], p["resultado_visitante"]
        return f"{emoji} {local} - {visitante} ({tag}: {gl}-{gv} {marca})"
    return f"{emoji} {local} - {visitante} ({tag})"


def descripcion(p: dict) -> str:
    ambito = f"{p['competicion_nombre']} · {etiqueta(p)}"
    lineas = [ambito,
              ("Estu en casa" if p["casa"] else "Estu fuera") + f" vs {p['rival']}"]
    if p["estado"] == "jugado":
        lineas.append(f"Resultado: Estu {p['resultado_estu']}-{p['resultado_rival']} "
                      + ("victoria ✅" if p["victoria"] else "derrota ❌"))
    else:
        dt = datetime.fromisoformat(p["inicio_madrid"])
        lineas.append(f"Inicio: {dt.strftime('%d/%m/%Y %H:%M')} (Madrid)")
    lineas.append(f"Acta FEB: {p['acta']}")
    return chr(10).join(lineas)


def sede_txt(p: dict) -> str:
    s = p.get("sede") or {}
    return ", ".join(x for x in (s.get("pabellon"), s.get("direccion")) if x)


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(partidos: list[dict]) -> str:
    now = datetime.now(MADRID).astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//estudiantes-calendario//ES",
         "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Movistar Estudiantes 26/27",
         "X-WR-TIMEZONE:Europe/Madrid"]
    for p in partidos:
        if "inicio_madrid" in p:
            start = datetime.fromisoformat(p["inicio_madrid"]).replace(tzinfo=MADRID)
        elif p["competicion"] == "liga":
            d, mo, y = map(int, p["fecha_jornada"].split("/"))
            start = datetime(y, mo, d, 12, 0, tzinfo=MADRID)
        else:
            raise ValueError(f"copa sin fecha: {p['uid']}")
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
        loc = sede_txt(p) or (CASA_PABELLON if p["casa"] else "")
        if loc:
            L.append(f"LOCATION:{esc(loc)}")
        L += ["TRANSP:TRANSPARENT", "STATUS:CONFIRMED", "SEQUENCE:0", "END:VEVENT"]
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"


def main() -> None:
    liga = parse_liga(fetch(LIGA_URL))
    assert len(liga) == 34, f"liga: esperaba 34 jornadas, hay {len(liga)}"
    copa = parse_copa(fetch(COPA_URL))
    assert len(copa) >= 1, "copa: el Estu no aparece en la pagina FEB"
    partidos = liga + copa
    # conservar inicio_madrid de pendientes que pasan a jugados (para fecha real del evento)
    if JSON_PATH.exists():
        prev = {p["uid"]: p for p in json.loads(JSON_PATH.read_text())}
        for p in partidos:
            old = prev.get(p["uid"])
            if old and p["estado"] == "jugado" and "inicio_madrid" in old:
                p["inicio_madrid"] = old["inicio_madrid"]
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(partidos, ensure_ascii=False, indent=2) + "\n")
    # sedes: caché por partido
    sedes = json.loads(SEDES_PATH.read_text()) if SEDES_PATH.exists() else {}
    for p in partidos:
        if p["feb_partido_id"] not in sedes:
            tag = etiqueta(p)
            try:
                sedes[p["feb_partido_id"]] = fetch_sede(p["feb_partido_id"])
                print(f"sede {tag}: {sedes[p['feb_partido_id']]}")
            except Exception as e:
                print(f"sede {tag}: ERROR {e}")
                sedes[p["feb_partido_id"]] = sedes.get(p["feb_partido_id"], {})
    SEDES_PATH.write_text(json.dumps(sedes, ensure_ascii=False, indent=2) + "\n")
    for p in partidos:
        if sedes.get(p["feb_partido_id"]):
            p["sede"] = sedes[p["feb_partido_id"]]
    JSON_PATH.write_text(json.dumps(partidos, ensure_ascii=False, indent=2) + "\n")
    ICS_PATH.write_text(to_ics(partidos))
    jug = sum(1 for p in partidos if p["estado"] == "jugado")
    print(f"liga={len(liga)} copa={len(copa)} jugados={jug} pendientes={len(partidos)-jug}")
    print(f"json={JSON_PATH} ics={ICS_PATH}")


if __name__ == "__main__":
    main()
