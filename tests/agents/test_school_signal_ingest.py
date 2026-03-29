import unittest

from briarwood.agents.school_signal.ingest import (
    TownSchoolTarget,
    build_school_signal_dataset,
    build_school_signal_dataset_from_workbook_rows,
)


class SchoolSignalIngestTests(unittest.TestCase):
    def test_build_school_signal_dataset_filters_to_targeted_towns(self) -> None:
        rows = [
            {
                "county_name": "Monmouth",
                "state": "NJ",
                "district_name": "Belmar School District",
                "school_name": "Belmar Elementary School",
                "achievement_index": "66",
                "growth_index": "63",
                "chronic_absenteeism_pct": "11.0",
                "student_teacher_ratio": "13.5",
            },
            {
                "county_name": "Monmouth",
                "state": "NJ",
                "district_name": "Sea Girt School District",
                "school_name": "Sea Girt Elementary",
                "achievement_index": "82",
                "growth_index": "77",
                "chronic_absenteeism_pct": "6.5",
                "student_teacher_ratio": "11.5",
            },
            {
                "county_name": "Ocean",
                "state": "NJ",
                "district_name": "Point Pleasant District",
                "school_name": "Point Pleasant Elementary",
                "achievement_index": "70",
                "growth_index": "68",
                "chronic_absenteeism_pct": "10.0",
                "student_teacher_ratio": "13.0",
            },
        ]
        targets = [
            TownSchoolTarget(
                name="Belmar",
                state="NJ",
                county="Monmouth",
                district_tokens=["belmar"],
                school_tokens=["belmar elementary"],
            ),
            TownSchoolTarget(
                name="Sea Girt",
                state="NJ",
                county="Monmouth",
                district_tokens=["sea girt"],
                school_tokens=["sea girt elementary"],
            ),
        ]

        dataset = build_school_signal_dataset(rows=rows, targets=targets, as_of="2026-03-29")

        self.assertEqual(len(dataset["towns"]), 2)
        self.assertEqual(dataset["towns"][0]["name"], "Belmar")
        self.assertEqual(dataset["towns"][1]["name"], "Sea Girt")
        self.assertEqual(dataset["towns"][0]["achievement_index"], 66.0)
        self.assertEqual(dataset["source_name"], "briarwood_school_signal_nj_spr_v1")

    def test_workbook_dataset_uses_targeted_rows_and_exclusions(self) -> None:
        sheet_rows = {
            "AccountabilityIndScoresSummativ": [
                {
                    "CountyName": "Monmouth",
                    "DistrictName": "Belmar Elementary School District",
                    "SchoolName": "Belmar Elementary",
                    "Student Group": "Schoolwide",
                    "IndicatorScore-ELAProficiency": "61.08",
                    "IndicatorScore-MathProficiency": "50.23",
                    "IndicatorScore-ELAGrowth": "43.71",
                    "IndicatorScore-MathGrowth": "25.86",
                },
                {
                    "CountyName": "Monmouth",
                    "DistrictName": "Wall Township Public School District",
                    "SchoolName": "West Belmar Elementary School",
                    "Student Group": "Schoolwide",
                    "IndicatorScore-ELAProficiency": "83.81",
                    "IndicatorScore-MathProficiency": "85.17",
                    "IndicatorScore-ELAGrowth": "76.81",
                    "IndicatorScore-MathGrowth": "66.26",
                },
            ],
            "ChronicAbsenteeism": [
                {
                    "CountyName": "Monmouth",
                    "DistrictName": "Belmar Elementary School District",
                    "SchoolName": "Belmar Elementary",
                    "StudentGroup": "Schoolwide",
                    "Chronic_Abs_Pct": "11.1",
                }
            ],
            "StudentToStaffRatios": [
                {
                    "CountyName": "Monmouth",
                    "DistrictName": "Belmar Elementary School District",
                    "SchoolName": "Belmar Elementary",
                    "Student_Teacher_School": "8:1",
                }
            ],
            "PSAT-SAT-ACTPerformance": [],
            "FederalGraduationRates": [],
        }
        targets = [
            TownSchoolTarget(
                name="Belmar",
                state="NJ",
                county="Monmouth",
                district_tokens=["belmar elementary school district"],
                school_tokens=["belmar elementary"],
                exclude_tokens=["west belmar"],
            )
        ]

        dataset = build_school_signal_dataset_from_workbook_rows(
            sheet_rows=sheet_rows,
            targets=targets,
            as_of="2026-03-29",
        )

        town = dataset["towns"][0]
        self.assertEqual(town["name"], "Belmar")
        self.assertEqual(town["achievement_index"], 55.66)
        self.assertEqual(town["growth_index"], 34.78)
        self.assertEqual(town["student_teacher_ratio"], 8.0)
        self.assertEqual(town["district_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
