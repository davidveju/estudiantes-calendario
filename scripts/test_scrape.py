#!/usr/bin/env python3
"""Tests sin red de los parsers y del generador ICS (stdlib unittest)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scrape  # noqa: E402


LIGA_FECHA = """Jornada 1 23/10/2026
<table>
<tr>
  <td><a href="Equipo.aspx?i=1010493">ESTU</a></td>
  <td><a href="Equipo.aspx?i=111">RIVAL</a></td>
  <td class="fecha"><a>25/10/2026&nbsp;<br/>18:00</a></td>
  <td><a href="Partido.aspx?p=123">x</a></td>
</tr>
</table>"""

LIGA_JUGADO = """Jornada 1 23/10/2026
<table>
<tr>
  <td><a href="Equipo.aspx?i=1010493">ESTU</a></td>
  <td><a href="Equipo.aspx?i=111">RIVAL</a></td>
  <td class="resultado"><a>80-70</a></td>
  <td><a href="Partido.aspx?p=123">x</a></td>
</tr>
</table>"""

COPA_TBD = """<select id="_ctl0_gruposDropDownList">
<option selected="selected" value="1">Play-offs 1/8 Final</option>
</select>
<select id="_ctl0_jornadasDropDownList">
<option selected="selected" value="2">Jornada 1(17/11/2026)</option>
</select>
<table><tr>
  <td><a href="Equipo.aspx?i=222">CACERES</a> -
      <a href="Equipo.aspx?i=1010493">ESTU</a></td>
  <td><a href="Partido.aspx?p=2550809">*-*</a></td>
  <td>Por determinar</td>
  <td></td>
</tr></table>"""

COPA_JUGADO = """<select id="_ctl0_gruposDropDownList">
<option selected="selected" value="1">Play-offs 1/16 Final</option>
</select>
<select id="_ctl0_jornadasDropDownList">
<option selected="selected" value="2">Jornada 1(20/10/2026)</option>
</select>
<table><tr>
  <td><a href="Equipo.aspx?i=333">COVIRAN GRANADA</a> -
      <a href="Equipo.aspx?i=1010493">ESTU</a></td>
  <td><a href="Partido.aspx?p=2543131">76-86</a></td>
  <td>20/10/2026</td>
  <td>20:30</td>
</tr></table>"""


class TestScore(unittest.TestCase):
    def test_marcador(self):
        self.assertEqual(scrape._score("78-65"), (78, 65))
        self.assertEqual(scrape._score("78 - 65"), (78, 65))
        self.assertEqual(scrape._score("106–76 (prórroga)"), (106, 76))

    def test_fecha_no_es_marcador(self):
        self.assertIsNone(scrape._score("12-10-2026"))
        self.assertIsNone(scrape._score("2026-10-12"))
        self.assertIsNone(scrape._score("*-*"))


class TestTitleCase(unittest.TestCase):
    def test_nombres(self):
        self.assertEqual(scrape.title_case("C.B. STARLABS MORÓN"), "CB Starlabs Morón")
        self.assertEqual(scrape.title_case("PARTIZÁN DE FUENLABRADA"), "Partizán de Fuenlabrada")
        self.assertEqual(scrape.title_case("PABELLÓN MUNICIPAL DE DEPORTES (PALENCIA)"),
                         "Pabellón Municipal de Deportes (Palencia)")


class TestRondaCopa(unittest.TestCase):
    def test_rondas(self):
        self.assertEqual(scrape._ronda_copa("Play-offs 1/16 Final", 1), ("1/16", 1))
        self.assertEqual(scrape._ronda_copa("Play-offs 1/8 Final", 1), ("1/8", 2))
        self.assertEqual(scrape._ronda_copa("Play-offs 1/4 Final", 1), ("1/4", 3))
        self.assertEqual(scrape._ronda_copa("Semifinal", 1), ("Semifinal", 4))
        self.assertEqual(scrape._ronda_copa("Final", 1), ("Final", 5))

    def test_grupo_desconocido_no_inventa_ronda(self):
        with self.assertRaises(ValueError):
            scrape._ronda_copa('FASE DE GRUPOS "A"', 1)


class TestSelects(unittest.TestCase):
    def test_grupo_no_lee_el_select_de_jornadas(self):
        html = """<select id="x_gruposDropDownList">
        <option value="1">Play-offs 1/8 Final</option></select>
        <select id="x_jornadasDropDownList">
        <option selected="selected">Jornada 1(17/11/2026)</option></select>"""
        self.assertEqual(scrape._grupo_copa(html), "Play-offs 1/8 Final")

    def test_grupo_ambiguo_falla(self):
        html = """<select id="x_gruposDropDownList">
        <option>Play-offs 1/8 Final</option>
        <option>Play-offs 1/4 Final</option></select>"""
        with self.assertRaises(ValueError):
            scrape._grupo_copa(html)


class TestPendiente(unittest.TestCase):
    def test_variantes(self):
        self.assertTrue(scrape._es_pendiente("Por determinar 19:00"))
        self.assertTrue(scrape._es_pendiente("APLAZADO"))
        self.assertFalse(scrape._es_pendiente("78-65"))


class TestParseLiga(unittest.TestCase):
    def test_fecha_con_nbsp(self):
        p = scrape.parse_liga(LIGA_FECHA)[0]
        self.assertEqual(p["inicio_madrid"], "2026-10-25T18:00:00")
        self.assertEqual(p["jornada"], 1)
        self.assertTrue(p["casa"])
        self.assertEqual(p["estado"], "pendiente")
        self.assertNotIn("fecha_provisional", p)

    def test_fecha_con_guiones_no_se_lee_como_marcador(self):
        html = LIGA_FECHA.replace("25/10/2026&nbsp;<br/>18:00", "25-10-2026<br/>18:00")
        p = scrape.parse_liga(html)[0]
        self.assertEqual(p["inicio_madrid"], "2026-10-25T18:00:00")
        self.assertEqual(p["estado"], "pendiente")

    def test_jugado_marca_hora_provisional(self):
        p = scrape.parse_liga(LIGA_JUGADO)[0]
        self.assertEqual(p["estado"], "jugado")
        self.assertEqual((p["resultado_estu"], p["resultado_rival"]), (80, 70))
        self.assertTrue(p["victoria"])
        self.assertTrue(p.get("fecha_provisional"))

    def test_duplicado_prefiere_jugado(self):
        html = LIGA_JUGADO.replace(
            "</table>",
            """<tr>
  <td><a href="Equipo.aspx?i=1010493">ESTU</a></td>
  <td><a href="Equipo.aspx?i=111">RIVAL</a></td>
  <td class="fecha"><a>25/10/2026<br/>18:00</a></td>
  <td><a href="Partido.aspx?p=123">x</a></td>
</tr></table>""")
        p = scrape.parse_liga(html)[0]
        self.assertEqual(p["estado"], "jugado")
        self.assertEqual((p["resultado_estu"], p["resultado_rival"]), (80, 70))


class TestParseCopa(unittest.TestCase):
    def test_tbd_usa_fecha_de_jornada(self):
        p = scrape.parse_copa(COPA_TBD)[0]
        self.assertEqual(p["uid"], "estu-2627-copa-j02@estudiantes-calendario")
        self.assertEqual(p["ronda"], "1/8")
        self.assertEqual(p["estado"], "pendiente")
        self.assertEqual(p["inicio_madrid"], "2026-11-17T12:00:00")
        self.assertTrue(p["fecha_provisional"])
        self.assertFalse(p["casa"])

    def test_jugado(self):
        p = scrape.parse_copa(COPA_JUGADO)[0]
        self.assertEqual(p["uid"], "estu-2627-copa-j01@estudiantes-calendario")
        self.assertEqual(p["ronda"], "1/16")
        self.assertEqual(p["estado"], "jugado")
        self.assertEqual((p["resultado_estu"], p["resultado_rival"]), (86, 76))
        self.assertTrue(p["victoria"])
        self.assertNotIn("fecha_provisional", p)


class TestFold(unittest.TestCase):
    def test_limites_y_multibyte(self):
        for s in ("A" * 74, "A" * 75, "A" * 76, "ñ" * 40, "🏀" * 30, "x" * 73 + "ñ"):
            line = "SUMMARY:" + s
            folded = scrape.fold_line(line)
            for trozo in folded.split("\r\n"):
                self.assertLessEqual(len(trozo.encode("utf-8")), 75)
            self.assertEqual(folded.replace("\r\n ", ""), line)


class TestICS(unittest.TestCase):
    def _evento(self, uid, **extra):
        p = {
            "uid": uid, "competicion": "liga", "competicion_nombre": "Primera FEB 26/27",
            "jornada": 1, "fecha_jornada": "01/01/2027", "casa": True, "rival": "Rival",
            "feb_partido_id": "1", "acta": "https://example.com/1", "estado": "pendiente",
            "inicio_madrid": "2027-01-01T12:00:00",
        }
        p.update(extra)
        return p

    def test_crlf_plegado_y_estado(self):
        ics = scrape.to_ics([
            self._evento("a@x"),
            self._evento("b@x", competicion="copa", ronda="1/8", casa=False,
                         fecha_jornada="Por determinar", inicio_madrid="2026-11-17T12:00:00",
                         fecha_provisional=True),
        ])
        data = ics.encode("utf-8")
        self.assertTrue(data.endswith(b"\r\n"))
        self.assertNotIn(b"\r\r\n", data)
        for linea in data.split(b"\r\n"):
            self.assertLessEqual(len(linea), 75)
        self.assertEqual(data.count(b"BEGIN:VEVENT"), 2)
        self.assertEqual(data.count(b"UID:"), 2)
        self.assertEqual(data.count(b"STATUS:TENTATIVE"), 1)

    def test_sin_fecha_se_omite(self):
        p = self._evento("c@x", fecha_jornada="Por determinar")
        p.pop("inicio_madrid")
        ics = scrape.to_ics([p])
        self.assertEqual(ics.count("BEGIN:VEVENT"), 0)


if __name__ == "__main__":
    unittest.main()
