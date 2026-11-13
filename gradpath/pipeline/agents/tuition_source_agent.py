"""Gather versioned school cost evidence; never present it as a live fee quote."""

import math

from build_reference_data import official_website


class TuitionSourceAgent:
    """Read College Scorecard's published figures and point to the school's site."""

    @staticmethod
    def _amount(value):
        try:
            amount = float(value)
            return amount if math.isfinite(amount) and amount >= 0 else None
        except (TypeError, ValueError):
            return None

    def gather(self, school):
        annual_in = self._amount(school.get("tuition_fees_in_state"))
        annual_out = self._amount(school.get("tuition_fees_out_of_state"))
        annual_cost = self._amount(school.get("cost_of_attendance_academic_year"))
        return {
            "school_name": str(school.get("school_name") or "School"),
            "official_website": official_website(school.get("official_website")),
            "source_url": "https://collegescorecard.ed.gov/data/",
            "source_year": str(school.get("source_year") or ""),
            "tuition_fees_in_state": annual_in,
            "tuition_fees_out_of_state": annual_out,
            "cost_of_attendance_academic_year": annual_cost,
            "monthly_tuition_in_state": round(annual_in / 12, 2) if annual_in is not None else None,
            "monthly_tuition_out_of_state": round(annual_out / 12, 2) if annual_out is not None else None,
            "monthly_cost_of_attendance": round(annual_cost / 12, 2) if annual_cost is not None else None,
            "monthly_basis": "12-month equivalent; not the school's billing schedule",
            "verification": "Open the official school website to confirm current tuition and mandatory fees.",
        }
