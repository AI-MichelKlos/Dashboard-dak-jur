"""Regression checks for title changes and corrupt dashboard data."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_jur_dashboard import DATA_END, DATA_START, ValidationError, validate


class DashboardValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.data = json.loads((ROOT / "data/dashboard-data.json").read_text(encoding="utf-8"))

    def with_data(self, data):
        before, payload = self.html.split(DATA_START, 1)
        _, after = payload.split(DATA_END, 1)
        return before + DATA_START + json.dumps(data) + DATA_END + after

    def test_current_dashboard_and_changed_title_pass(self):
        validate(self.html, self.data)
        validate(self.html.replace("JUR - Arbejdsmarkedsoverblik", "En ny overskrift"), self.data)

    def test_missing_structure_and_data_block_fail(self):
        for marker in ('id="dak-analyse-jur"', 'id="kpiGrid"',
                       'id="unemploymentPercentChart"', 'id="bankruptciesChart"', DATA_START):
            with self.subTest(marker=marker), self.assertRaises(ValidationError):
                validate(self.html.replace(marker, ""), self.data)

    def test_stale_html_and_invalid_embedded_json_fail(self):
        data = copy.deepcopy(self.data)
        data["meta"]["versionDate"] = "Ændret uden at opdatere HTML"
        with self.assertRaisesRegex(ValidationError, "indlejret DATA afviger"):
            validate(self.html, data)
        with self.assertRaisesRegex(ValidationError, "ugyldig JSON"):
            validate(self.html.replace(DATA_START, DATA_START + "!", 1), self.data)

    def test_missing_periods_totals_and_wrong_kpis_fail(self):
        mutations = (
            (lambda s: s["labels"].clear(), "perioder mangler"),
            (lambda s: s["labels"].__setitem__(-1, "1900M01"), "grafens seneste periode"),
            (lambda s: s["total"].__setitem__(-1, None), "seneste værdi mangler"),
            (lambda s: s["total"].pop(), "antal værdier"),
            (lambda s: s["kpi"].__setitem__("period", "1900M01"), "KPI-perioden"),
            (lambda s: s["kpi"].__setitem__("value", -1), "KPI-værdien"),
        )
        for section in ("unemploymentPercent", "bankruptcies"):
            for mutate, error in mutations:
                with self.subTest(section=section, error=error):
                    data = copy.deepcopy(self.data)
                    mutate(data["sections"][section])
                    with self.assertRaisesRegex(ValidationError, error):
                        validate(self.with_data(data), data)

    def test_akasse_missing_values_fail_and_zero_passes(self):
        for value in (None, 0):
            data = copy.deepcopy(self.data)
            values = next(iter(data["sections"]["unemploymentPercent"]["byAkasse"].values()))
            values[-1] = value
            if value is None:
                with self.assertRaisesRegex(ValidationError, "AUP03 / .*seneste værdi mangler"):
                    validate(self.with_data(data), data)
            else:
                validate(self.with_data(data), data)

    def test_failed_or_missing_source_status_fails(self):
        for source in ("AUP03", "KONK3"):
            for missing in (False, True):
                data = copy.deepcopy(self.data)
                if missing:
                    del data["meta"]["sourceStatus"][source]
                else:
                    data["meta"]["sourceStatus"][source]["state"] = "failed"
                with self.subTest(source=source, missing=missing):
                    with self.assertRaisesRegex(ValidationError, source):
                        validate(self.with_data(data), data)

    def test_partial_update_cannot_pass(self):
        data = copy.deepcopy(self.data)
        data["meta"]["updateStatus"].update(state="partial", failed=["sanktioner"])
        with self.assertRaisesRegex(ValidationError, "ikke fuldført"):
            validate(self.with_data(data), data)


if __name__ == "__main__":
    unittest.main()
