#!/usr/bin/env python3
"""Calendario Movistar Estudiantes (masc, 26/27) -> partidos.json + estudiantes.ics.

Fuentes FEB:
  - Liga (Primera FEB): competiciones.feb.es/estadisticas/Calendario.aspx
      celda 'resultado' con marcador  => jugado
      celda 'fecha' con DIA dd/mm/aaaa hh:mm => pendiente (hora Madrid)
  - Copa (eliminatorias a partido unico): www.feb.es/competiciones/resultados/copaespaa/73/2026
      tabla Equipos | Resultado (*-* = pendiente) | Fecha | Hora
      La FEB reutiliza "Jornada 1" en cada fase (1/16, 1/8...): la ronda real
      sale del desplegable de grupos ("Play-offs 1/8 Final"). "Por determinar"
      en fecha => pendiente con fecha provisional de la jornada.
Solo stdlib. UIDs estables por jornada/ronda para que Google actualice sin duplicar.
Playoffs (13/05-06/06/2027): cuando la FEB publique su pagina, anadir URL + parse_*
siguiendo el patron de la copa.
"""
import html as _html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from http.client import HTTPException
from zoneinfo import ZoneInfo
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # repo root (script vive en scripts/)
JSON_PATH = BASE / "datos" / "partidos.json"
SEDES_PATH = BASE / "datos" / "sedes.json"
FECHAS_PATH = BASE / "datos" / "fechas_reales.json"
ICS_PATH = BASE / "estudiantes.ics"
LIGA_URL = "https://competiciones.feb.es/estadisticas/Calendario.aspx"
COPA_URL = "https://www.feb.es/competiciones/resultados/copaespaa/73/2026"
ESTU_ID = "1010493"
MADRID = ZoneInfo("Europe/Madrid")

LIGA_NOMBRE = "Primera FEB 26/27"
COPA_NOMBRE = "Copa España 26/27"
RONDAS_COPA = {1: "1/16", 2: "1/8", 3: "1/4", 4: "Semifinal", 5: "Final"}
RONDA_A_JNUM = {v: k for k, v in RONDAS_COPA.items()}
CASA_PABELLON = "Movistar Arena, Madrid"
ESTU_RE = re.compile(r"[?&]i=" + re.escape(ESTU_ID) + r"\b", re.I)

# Resultados que significan "pendiente" aunque no haya marcador (FEB varia el texto).
PENDIENTE_TXT = {"*-*", "* - *", "-", "", "POR DETERMINAR", "PDT",
                 "SUSP", "SUSP.", "SUSPENDIDO", "PP", "APL", "APLAZADO", "APLAZADA",
                 "DESC", "DESCANSO"}


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    # GitHub Actions lo muestra como aviso; en local sale como texto.
    print(f"::warning::{msg}", flush=True)


def _limpia(txt: str) -> str:
    """Texto de celda: sin tags, entidades decodificadas, nbsp->espacio."""
    return _html.unescape(re.sub(r"<[^>]+>", " ", txt)).replace("\xa0", " ").strip()


def _no_reintentable(e: Exception) -> bool:
    return (isinstance(e, urllib.error.HTTPError)
            and e.code not in (408, 425, 429, 500, 502, 503, 504))


def fetch(url: str, retries: int = 3, timeout: int = 30) -> str:
    """Descarga con reintentos solo ante fallos transitorios (5xx/429/red)."""
    last = None
    for i in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (calendario-estu)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                charset = r.headers.get_content_charset() or "utf-8"
                return r.read().decode(charset, "replace")
        except Exception as e:
            last = e
            log(f"fetch {url}: intento {i}/{retries} fallo ({e})")
            if _no_reintentable(e) or i >= retries:
                break
            time.sleep(2 * i)
    raise ValueError(f"fetch: {url} fallo tras {retries} intentos ({last})")


def fetch_sede(pid: str, retries: int = 2, timeout: int = 15) -> dict:
    """Pabellón + dirección desde la ficha del partido. {} si no hay pista (reintentable)."""
    last: Exception | None = None
    for i in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                f"https://baloncestoenvivo.feb.es/Partido.aspx?p={pid}",
                headers={"User-Agent": "Mozilla/5.0 (calendario-estu)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                charset = r.headers.get_content_charset() or "utf-8"
                h = r.read().decode(charset, "replace")
            m = re.search(r'<div[^>]*\bclass\s*=\s*["\'][^"\']*\bpista\b[^"\']*["\'][^>]*>'
                          r'(.*?)</div\s*>', h, re.S | re.I)
            if not m:
                return {}
            pab = re.search(r'class\s*=\s*["\'][^"\']*\bpabellon\b[^"\']*["\'][^>]*>'
                            r'(.*?)</(span|div)\s*>', m.group(1), re.S | re.I)
            drc = re.search(r'class\s*=\s*["\'][^"\']*\bdireccion\b[^"\']*["\'][^>]*>'
                            r'(.*?)</(span|div)\s*>', m.group(1), re.S | re.I)
            pab_txt = title_case(_limpia(pab.group(1))) if pab and _limpia(pab.group(1)) else ""
            drc_txt = _limpia(drc.group(1)) if drc and _limpia(drc.group(1)) else ""
            if not pab_txt and not drc_txt:
                return {}
            return {"pabellon": pab_txt, "direccion": drc_txt}
        except (urllib.error.URLError, TimeoutError, HTTPException, OSError) as e:
            last = e
            log(f"sede pid={pid}: intento {i}/{retries} fallo ({e})")
            if i < retries:
                time.sleep(2 * i)
        finally:
            time.sleep(1)
    raise ValueError(f"sede pid={pid} fallo tras {retries} intentos ({last})")


def _cap_word(w: str, minus: set, siglas: set, is_first: bool) -> str:
    key = re.sub(r"[.\-'/·]", "", w).lower()
    if key in siglas:
        return re.sub(r"[.\-'/·]", "", w).upper()
    if key in minus and not is_first:
        return w.lower()
    # Capitaliza la primera letra alfabetica, respeta guiones/apostrofes.
    def _cap(seg: str) -> str:
        m = re.search(r"[A-Za-zÀ-ÿ]", seg)
        if not m:
            return seg
        i = m.start()
        return seg[:i] + seg[i].upper() + seg[i + 1:].lower()
    return "".join(_cap(s) if j % 2 == 0 else s
                   for j, s in enumerate(re.split(r"([-'/·])", w)))


def title_case(s: str) -> str:
    minus = {"de", "del", "la", "el", "los", "las", "en", "y", "a", "al"}
    siglas = {"cb", "cd", "ad", "sd", "xb", "alb", "bca", "hla"}
    palabras = s.strip().split()
    return " ".join(_cap_word(w, minus, siglas, i == 0) for i, w in enumerate(palabras))


def _score(texto: str) -> tuple[int, int] | None:
    m = re.search(r"(\d+)\s*[-–—]\s*(\d+)", texto)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _es_pendiente(texto: str) -> bool:
    return texto.strip().upper() in PENDIENTE_TXT


def parse_liga(html: str) -> list[dict]:
    h2 = _html.unescape(html).replace("\xa0", " ")
    blocks = re.findall(r"Jornada\s+(\d+)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})(.*?)(?=Jornada\s+\d+\s+\d{1,2}[/-]|$)",
                        h2, re.S | re.I)
    if not blocks:
        raise ValueError("liga: no se encontraron bloques de jornada (cambio la pagina FEB)")
    partidos = []
    for jnum, jdate_raw, body in blocks:
        jdate = re.sub(r"-", "/", jdate_raw)
        for r in re.findall(r"<tr[^>]*>(.*?)</tr\s*>", body, re.S | re.I):
            if not ESTU_RE.search(r):
                continue
            snippet = re.sub(r"\s+", " ", r)[:2000]
            m_pid = re.search(r"Partido\.aspx\?p=(\d+)\b", r, re.I)
            if not m_pid:
                raise ValueError(f"liga: sin partido id J{jnum}: {snippet[:500]}")
            pid = m_pid.group(1)
            equipos = re.findall(r"Equipo\.aspx\?i=(\d+)\b[^>]*>\s*([^<]+?)\s*</a>", r, re.I)
            if len(equipos) < 2:
                raise ValueError(f"liga: sin 2 equipos J{jnum} pid={pid}: {snippet[:500]}")
            ids = [e[0] for e in equipos]
            if ESTU_ID not in ids:
                raise ValueError(f"liga: Estu no esta entre los ids J{jnum} pid={pid}: {ids}")
            casa = (ids[0] == ESTU_ID)
            rival_raw = equipos[1][1] if casa else equipos[0][1]
            m = re.search(r'<td[^>]*\bclass\s*=\s*["\']?[^"\'<>]*\b(resultado|fecha)\b[^"\'<>]*'
                          r'["\']?[^>]*>\s*<a[^>]*>(.*?)</a>', r, re.S | re.I)
            if not m:
                raise ValueError(f"liga: celda resultado/fecha no encontrada J{jnum} pid={pid}: {snippet[:500]}")
            cell = re.sub(r"\s+", " ", m.group(2)).strip()
            t = _limpia(cell)
            score = _score(t)
            p = {
                "jornada": int(jnum),
                "fecha_jornada": jdate,
                "uid": f"estu-2627-j{int(jnum):02d}@estudiantes-calendario",
                "competicion": "liga",
                "competicion_nombre": LIGA_NOMBRE,
                "casa": casa,
                "rival": title_case(_limpia(rival_raw)),
                "feb_partido_id": pid,
                "acta": f"https://baloncestoenvivo.feb.es/Partido.aspx?p={pid}",
                "estado": "jugado" if score else "pendiente",
            }
            if score:
                gl, gv = score
                p["resultado_local"], p["resultado_visitante"] = gl, gv
                pe, pr = (gl, gv) if casa else (gv, gl)
                p["resultado_estu"], p["resultado_rival"] = pe, pr
                p["victoria"] = pe > pr
            else:
                dm = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})\s*(?:<br\s*/?>\s*)?(\d{1,2}:\d{2})?",
                               cell, re.I)
                if dm:
                    d, mo, y = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
                    hhmm = dm.group(4) or "12:00"
                    hh, mm = map(int, hhmm.split(":"))
                    p["inicio_madrid"] = f"{y:04d}-{mo:02d}-{d:02d}T{hh:02d}:{mm:02d}:00"
                    if not dm.group(4):
                        p["fecha_provisional"] = True
                elif _es_pendiente(t) or not t:
                    # Aplazado/suspendido sin fecha en la celda: provisional con la semana.
                    d, mo, y = map(int, jdate.split("/"))
                    p["inicio_madrid"] = f"{y:04d}-{mo:02d}-{d:02d}T12:00:00"
                    p["fecha_provisional"] = True
                    warn(f"liga: J{jnum} pid={pid} sin fecha ({t!r}); provisional {jdate}")
                else:
                    raise ValueError(f"liga: fecha no parseable J{jnum} pid={pid}: {cell!r} (fila: {snippet[:500]})")
            partidos.append(p)
    # Dedup por UID: la FEB a veces duplica/aplaza filas; nunca emitir duplicados.
    por_uid: dict[str, dict] = {}
    for p in partidos:
        if p["uid"] in por_uid and por_uid[p["uid"]]["feb_partido_id"] != p["feb_partido_id"]:
            warn(f"liga: UID duplicado {p['uid']} pids "
                 f"{por_uid[p['uid']]['feb_partido_id']} vs {p['feb_partido_id']}; me quedo con el ultimo")
        por_uid[p["uid"]] = p
    partidos = sorted(por_uid.values(), key=lambda p: p["jornada"])
    return partidos


def _grupo_copa(html: str) -> str:
    """Texto del desplegable de grupos seleccionado, ej 'Play-offs 1/8 Final'."""
    m = re.search(r'gruposDropDownList.*?<option[^>]*\bselected\b[^>]*>(.*?)</option>', html, re.S | re.I)
    if not m:
        return ""
    return re.sub(r"\s+", " ", _html.unescape(m.group(1)).replace("\xa0", " ")).strip()


def _jornada_copa_seleccionada(html: str) -> tuple[int, str]:
    """(numero, fecha dd/mm/aaaa o '') de la jornada seleccionada en la copa."""
    m = re.search(r'jornadasDropDownList.*?<option[^>]*\bselected\b[^>]*>\s*Jornada\s+(\d+)\s*'
                  r'(?:\((\d{1,2}/\d{1,2}/\d{4})\))?', html, re.S | re.I)
    if m:
        return int(m.group(1)), (m.group(2) or "")
    # Fallback: preferir la option marcada como selected, no la menor.
    mejor: tuple[int, str] | None = None
    for om in re.finditer(r"<option([^>]*)>\s*Jornada\s+(\d+)\s*(?:\((\d{1,2}/\d{1,2}/\d{4})\))?",
                          html, re.S | re.I):
        attrs, num, fec = om.group(1), int(om.group(2)), (om.group(3) or "")
        if re.search(r"\bselected\b", attrs, re.I):
            return num, fec
        if mejor is None:
            mejor = (num, fec)
    if mejor is not None:
        warn("copa: jornada sin selected; uso la primera encontrada")
        return mejor
    raise ValueError("copa: no se encontro ninguna jornada (cambio la pagina FEB)")


def _ronda_copa(grupo_txt: str, jnum_fallback: int) -> tuple[str, int]:
    """Ronda real desde el grupo. La FEB reutiliza Jornada 1 en cada fase."""
    g = grupo_txt.upper()
    if "1/16" in g or "DIECISEIS" in g:
        return "1/16", RONDA_A_JNUM["1/16"]
    if "1/8" in g or ("OCTAVOS" in g and "DIECISEIS" not in g):
        return "1/8", RONDA_A_JNUM["1/8"]
    if "1/4" in g or "CUARTO" in g:
        return "1/4", RONDA_A_JNUM["1/4"]
    if "SEMIFINAL" in g or re.search(r"\bSEMI\b", g):
        return "Semifinal", RONDA_A_JNUM["Semifinal"]
    if "FINAL" in g:
        return "Final", RONDA_A_JNUM["Final"]
    if not grupo_txt.strip():
        # Sin grupo no se inventa ronda: evita colisionar con el historico real.
        warn(f"copa: sin grupo en el HTML, uso J{jnum_fallback} sin mapear a ronda")
        return f"J{jnum_fallback}", jnum_fallback
    warn(f"copa: grupo no reconocido ({grupo_txt!r}), uso J{jnum_fallback} como ronda")
    return RONDAS_COPA.get(jnum_fallback, f"J{jnum_fallback}"), jnum_fallback


def _celdas(r: str) -> list[str]:
    return [_limpia(c) for c in re.findall(r"<td[^>]*>(.*?)</td\s*>", r, re.S | re.I)]


def parse_copa(html: str) -> list[dict]:
    """Copa España: eliminatorias a partido unico; fecha+hora en columnas propias.

    Acepta 'Por determinar' en fecha/hora: deja el partido pendiente con fecha
    provisional de la jornada (dropdown) para no tumbar toda la ejecucion.
    Si el Estu no esta en la fase actual (eliminado o aun no publicada), devuelve [].
    """
    grupo_txt = _grupo_copa(html)
    j_jornada, fecha_dropdown = _jornada_copa_seleccionada(html)
    ronda, jnum = _ronda_copa(grupo_txt, j_jornada)
    log(f"copa: fase={grupo_txt!r} jornada={j_jornada} fecha_jornada={fecha_dropdown!r} => ronda={ronda} uid_j={jnum:02d}")

    partidos = []
    filas = re.findall(r"<tr[^>]*>(.*?)</tr\s*>", html, re.S | re.I)
    if not filas:
        raise ValueError("copa: sin filas <tr> (cambio la pagina FEB)")
    for r in filas:
        if not ESTU_RE.search(r) or "equipo.aspx" not in r.lower():
            continue
        snippet = re.sub(r"\s+", " ", r)[:2000]
        eq = re.search(r"Equipo\.aspx\?i=(\d+)\b[^>]*>\s*([^<]+?)\s*</a>\s*-\s*"
                       r"<a[^>]*Equipo\.aspx\?i=(\d+)\b[^>]*>\s*([^<]+?)\s*</a>", r, re.S | re.I)
        rs = re.search(r"Partido\.aspx\?p=(\d+)\b[^>]*>(.*?)</a>", r, re.S | re.I)
        if not (eq and rs):
            raise ValueError(
                f"copa: fila del Estu no parseable (eq={bool(eq)} rs={bool(rs)}): {snippet[:1000]}")
        id_loc, nom_loc, id_vis, nom_vis = eq.groups()
        pid = rs.group(1)
        res_txt = _limpia(rs.group(2))
        celdas = _celdas(r)
        fecha_raw = next((c for c in celdas
                          if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", c)
                          or c.upper() == "POR DETERMINAR"), "")
        hora_m = next((re.search(r"(\d{1,2}:\d{2})", c) for c in celdas
                       if re.search(r"\d{1,2}:\d{2}", c)), None)
        hora_raw = hora_m.group(1) if hora_m else ""
        if not fecha_raw:
            raise ValueError(f"copa: sin fecha en la fila pid={pid}: {snippet[:1000]}")
        casa = (id_loc == ESTU_ID)
        score = _score(res_txt)
        if not (score or _es_pendiente(res_txt)):
            warn(f"copa: resultado desconocido pid={pid}: {res_txt!r}; se trata como pendiente")
        tbd = (fecha_raw.upper() == "POR DETERMINAR")
        fecha_jornada = fecha_dropdown or ("" if tbd else fecha_raw)
        if not fecha_jornada and tbd:
            warn(f"copa: {ronda} pid={pid} sin fecha ni fecha de jornada, se crea sin inicio")
            fecha_jornada = "Por determinar"
        p = {
            "jornada": jnum,
            "ronda": ronda,
            "fecha_jornada": fecha_jornada if fecha_jornada else fecha_raw,
            "uid": f"estu-2627-copa-j{jnum:02d}@estudiantes-calendario",
            "competicion": "copa",
            "competicion_nombre": COPA_NOMBRE,
            "casa": casa,
            "rival": title_case(_limpia(nom_vis if casa else nom_loc)),
            "feb_partido_id": pid,
            "acta": f"https://www.feb.es/competiciones/Partido.aspx?p={pid}",
            "estado": "jugado" if score else "pendiente",
        }
        if tbd:
            if fecha_dropdown:
                d, mo, y = map(int, fecha_dropdown.split("/"))
                p["inicio_madrid"] = f"{y:04d}-{mo:02d}-{d:02d}T12:00:00"
                p["fecha_provisional"] = True
            # else: sin inicio_madrid; to_ics/descripcion lo gestionan
        else:
            d, mo, y = map(int, fecha_raw.split("/"))
            hh, mm = map(int, (hora_raw or "12:00").split(":"))
            p["inicio_madrid"] = f"{y:04d}-{mo:02d}-{d:02d}T{hh:02d}:{mm:02d}:00"
            if not hora_raw:
                p["fecha_provisional"] = True
        if score:
            gl, gv = score
            p["resultado_local"], p["resultado_visitante"] = gl, gv
            pe, pr = (gl, gv) if casa else (gv, gl)
            p["resultado_estu"], p["resultado_rival"] = pe, pr
            p["victoria"] = pe > pr
        partidos.append(p)
    if not partidos:
        warn("copa: el Estu no aparece en la fase actual (eliminado o fase nueva sin publicar); se conserva el historico")
    por_uid: dict[str, dict] = {}
    for p in partidos:
        if p["uid"] in por_uid and por_uid[p["uid"]]["feb_partido_id"] != p["feb_partido_id"]:
            warn(f"copa: UID duplicado {p['uid']}; me quedo con el ultimo")
        por_uid[p["uid"]] = p
    return list(por_uid.values())


def etiqueta(p: dict) -> str:
    if p.get("competicion") == "copa":
        return f"Copa {p.get('ronda') or ('J' + str(p.get('jornada', '?')))}"
    return f"J{p.get('jornada', '?')}"


def resumen(p: dict) -> str:
    emoji = "🏆" if p.get("competicion") == "copa" else "🏀"
    tag = etiqueta(p)
    local = "Estu" if p.get("casa") else p.get("rival", "Rival")
    visitante = p.get("rival", "Rival") if p.get("casa") else "Estu"
    if p.get("estado") == "jugado" and "resultado_local" in p and "resultado_visitante" in p:
        marca = "✅" if p.get("victoria") else "❌"
        gl, gv = p["resultado_local"], p["resultado_visitante"]
        return f"{emoji} {local} - {visitante} ({tag}: {gl}-{gv} {marca})"
    return f"{emoji} {local} - {visitante} ({tag})"


def descripcion(p: dict) -> str:
    ambito = f"{p.get('competicion_nombre', '')} · {etiqueta(p)}"
    lineas = [ambito,
              (("Estu en casa" if p.get("casa") else "Estu fuera") + f" vs {p.get('rival', 'Rival')}")]
    if p.get("estado") == "jugado" and "resultado_estu" in p and "resultado_rival" in p:
        lineas.append(f"Resultado: Estu {p['resultado_estu']}-{p['resultado_rival']} "
                      + ("victoria ✅" if p.get("victoria") else "derrota ❌"))
    else:
        dt_raw = p.get("inicio_madrid") or ""
        try:
            dt = datetime.fromisoformat(dt_raw) if dt_raw else None
        except ValueError:
            dt = None
        if dt is not None:
            if p.get("fecha_provisional"):
                lineas.append(f"Inicio provisional: {dt.strftime('%d/%m/%Y %H:%M')} (Madrid, por confirmar FEB)")
            else:
                lineas.append(f"Inicio: {dt.strftime('%d/%m/%Y %H:%M')} (Madrid)")
        else:
            fj = p.get("fecha_jornada", "")
            if re.match(r"\d{1,2}/\d{1,2}/\d{4}", fj or ""):
                lineas.append(f"Fecha por determinar (semana del {fj}, por confirmar FEB)")
            else:
                lineas.append("Fecha por determinar (por confirmar FEB)")
    lineas.append(f"Acta FEB: {p.get('acta', '')}")
    return chr(10).join(lineas)


def sede_txt(p: dict) -> str:
    s = p.get("sede") or {}
    return ", ".join(x for x in (s.get("pabellon"), s.get("direccion")) if x)


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold_line(line: str, limit: int = 75) -> str:
    """Pliega una linea ICS por octetos UTF-8 (RFC 5545 §3.1) sin partir multibyte."""
    raw = line.encode("utf-8")
    if len(raw) <= limit:
        return line
    partes: list[str] = []
    chunk = raw[:limit]
    # Retrocede hasta un borde de caracter UTF-8.
    while chunk and (chunk[-1] & 0xC0) == 0x80:
        chunk = chunk[:-1]
    partes.append(chunk.decode("utf-8"))
    resto = raw[len(chunk):]
    while resto:
        chunk = resto[:limit - 1]
        while chunk and (chunk[-1] & 0xC0) == 0x80:
            chunk = chunk[:-1]
        partes.append(" " + chunk.decode("utf-8"))
        resto = resto[len(chunk):]
    return "\r\n".join(partes)


def _inicio_evento(p: dict):
    """Fecha del evento: inicio real, o fecha_jornada a las 12:00, o None si no hay nada."""
    dt_raw = p.get("inicio_madrid") or ""
    if dt_raw:
        try:
            dt = datetime.fromisoformat(dt_raw)
        except ValueError:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=MADRID, fold=0)
        return dt.astimezone(MADRID)
    fj = p.get("fecha_jornada", "")
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", fj or "")
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d, 12, 0, tzinfo=MADRID)
        except ValueError:
            return None
    return None


def to_ics(partidos: list[dict]) -> str:
    # UIDs duplicados = duplicados en Google Calendar: fallar antes de publicar.
    conteo = Counter(p.get("uid", "?") for p in partidos)
    dups = sorted(u for u, n in conteo.items() if n > 1)
    if dups:
        raise ValueError(f"ics: UIDs duplicados {dups}")
    now = datetime.now(MADRID).astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//estudiantes-calendario//ES",
         "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Movistar Estudiantes 26/27",
         "X-WR-TIMEZONE:Europe/Madrid"]
    orden = sorted(partidos, key=lambda p: (_inicio_evento(p) or datetime.max.replace(tzinfo=MADRID)))
    omitidos = 0
    for p in orden:
        try:
            uid = p.get("uid") or ""
            acta = p.get("acta") or ""
            if not uid or not acta:
                raise KeyError(f"uid/acta ausentes ({uid!r})")
            start = _inicio_evento(p)
            if start is None:
                raise ValueError("sin fecha (TBD sin provisional)")
            end = start + timedelta(hours=2)
            su, eu = start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))
            summary, desc = resumen(p), descripcion(p)
            loc = sede_txt(p) or (CASA_PABELLON if p.get("casa") else "")
            # SEQUENCE fijo a 0: Google/Apple actualizan por UID+DTSTAMP.
            estado = "TENTATIVE" if p.get("fecha_provisional") else "CONFIRMED"
            for content in ["BEGIN:VEVENT",
                            f"UID:{uid}",
                            f"DTSTAMP:{now}",
                            f"DTSTART:{su.strftime('%Y%m%dT%H%M%SZ')}",
                            f"DTEND:{eu.strftime('%Y%m%dT%H%M%SZ')}",
                            f"SUMMARY:{esc(summary)}",
                            f"DESCRIPTION:{esc(desc)}",
                            f"URL:{acta}"] + ([f"LOCATION:{esc(loc)}"] if loc else []) + [
                            "TRANSP:TRANSPARENT", f"STATUS:{estado}", "SEQUENCE:0", "END:VEVENT"]:
                L.append(fold_line(content))
        except Exception as e:
            warn(f"ics: se omite {p.get('uid', '?')}: {e}")
            omitidos += 1
            continue
    if omitidos:
        warn(f"ics: {omitidos} evento(s) omitido(s)")
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"


def _cargar_previo() -> list[dict]:
    if not JSON_PATH.exists():
        return []
    try:
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        warn(f"previo {JSON_PATH} ilegible ({e}); se sigue sin historico")
        return []


def _escritura_atomica(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def main() -> None:
    prev = _cargar_previo()
    prev_by_uid = {p["uid"]: p for p in prev if isinstance(p, dict) and "uid" in p}
    prev_liga = [p for p in prev if isinstance(p, dict) and p.get("competicion") == "liga"]
    prev_copa = [p for p in prev if isinstance(p, dict) and p.get("competicion") == "copa"]
    feb_fallback = False

    try:
        liga = parse_liga(fetch(LIGA_URL))
        if len(liga) != 34:
            raise ValueError(f"liga: esperaba 34 jornadas, hay {len(liga)}")
    except Exception as e:
        if prev_liga:
            warn(f"liga: fallo ({e}); se reutilizan {len(prev_liga)} partidos previos y no se tumba la ejecucion")
            liga = prev_liga
            feb_fallback = True
        else:
            raise

    try:
        copa_nueva = parse_copa(fetch(COPA_URL))
    except Exception as e:
        if prev_copa:
            warn(f"copa: fallo ({e}); se conserva el historico ({len(prev_copa)}) y no se tumba la ejecucion")
            copa_nueva = []
            feb_fallback = True
        else:
            raise

    # Historico de copa: la pagina FEB solo muestra la fase actual; conservar rondas viejas
    uids_nuevos = {p["uid"] for p in copa_nueva}
    duplicadas = [u for u in uids_nuevos if u in {p["uid"] for p in liga}]
    if duplicadas:
        raise ValueError(f"UIDs de copa colisionan con liga: {duplicadas}")
    copa_hist = [p for p in prev_copa if isinstance(p, dict) and p.get("uid") not in uids_nuevos]
    if copa_nueva:
        log(f"copa: nueva={len(copa_nueva)} historico_conservado={len(copa_hist)}")
    elif copa_hist:
        log(f"copa: sin novedades, historico={len(copa_hist)}")
    copa = copa_hist + copa_nueva

    partidos = liga + copa
    # conservar inicio_madrid de pendientes que pasan a jugados (para fecha real del evento)
    for p in partidos:
        old = prev_by_uid.get(p["uid"])
        if old and p["estado"] == "jugado" and "inicio_madrid" in old and "inicio_madrid" not in p:
            p["inicio_madrid"] = old["inicio_madrid"]
        # No pisar una hora real ya publicada con un provisional TBD
        if old and not old.get("fecha_provisional") and p.get("fecha_provisional"):
            if old.get("inicio_madrid"):
                p["inicio_madrid"] = old["inicio_madrid"]
                p.pop("fecha_provisional", None)
    # rescates manuales verificados (partidos jugados antes del primer scrape): mandan sobre todo
    if FECHAS_PATH.exists():
        try:
            seed = json.loads(FECHAS_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            warn(f"seed {FECHAS_PATH} ilegible ({e})")
            seed = {}
        if isinstance(seed, dict):
            for k, v in seed.items():
                if k.startswith("_"):
                    continue
                try:
                    datetime.fromisoformat(v)
                except Exception:
                    warn(f"seed: {k} con fecha invalida ({v!r}); se ignora")
                    continue
                for p in partidos:
                    if p["uid"] == k:
                        p["inicio_madrid"] = v
                        p.pop("fecha_provisional", None)
    # Validar UIDs antes de tocar el disco: nada de JSON nuevo + ICS viejo.
    conteo = Counter(p.get("uid", "?") for p in partidos)
    dups = sorted(u for u, n in conteo.items() if n > 1)
    if dups:
        raise ValueError(f"UIDs duplicados {dups}")
    # sedes: caché por partido (un fallo de sede nunca tumba la ejecucion)
    try:
        sedes = json.loads(SEDES_PATH.read_text(encoding="utf-8")) if SEDES_PATH.exists() else {}
        if not isinstance(sedes, dict):
            warn(f"sedes {SEDES_PATH} no es un objeto; se empieza vacio")
            sedes = {}
    except Exception as e:
        warn(f"sedes {SEDES_PATH} ilegible ({e}); se empieza vacio")
        sedes = {}
    for p in partidos:
        if not sedes.get(p["feb_partido_id"]):
            tag = etiqueta(p)
            try:
                sedes[p["feb_partido_id"]] = fetch_sede(p["feb_partido_id"])
                log(f"sede {tag}: {sedes[p['feb_partido_id']]}")
            except Exception as e:
                warn(f"sede {tag} pid={p['feb_partido_id']}: ERROR {e}")
                sedes[p["feb_partido_id"]] = sedes.get(p["feb_partido_id"], {})
    for p in partidos:
        if sedes.get(p["feb_partido_id"]):
            p["sede"] = sedes[p["feb_partido_id"]]
    ics = to_ics(partidos)
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    _escritura_atomica(JSON_PATH, (json.dumps(partidos, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    _escritura_atomica(SEDES_PATH, (json.dumps(sedes, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    _escritura_atomica(ICS_PATH, ics.encode("utf-8"))
    jug = sum(1 for p in partidos if p["estado"] == "jugado")
    log(f"liga={len(liga)} copa={len(copa)} jugados={jug} pendientes={len(partidos)-jug}")
    log(f"json={JSON_PATH} ics={ICS_PATH}")
    if feb_fallback:
        warn("FEB_FALLBACK=true: una fuente fallo y se uso historico; revisar logs")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr, flush=True)
        raise
