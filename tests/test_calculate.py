"""calculate: right answers, unsafe input refused, units converted.
Unit tests skip themselves when pint isn't installed.

    python -m unittest discover tests        (from the repo folder)
"""
import importlib.util
import os
import sys
import unittest

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from tools import calc  # noqa: E402

HAVE_PINT = importlib.util.find_spec("pint") is not None


def answer(expression):
    return calc._calculate(expression).rsplit(" = ", 1)[-1]


class Math(unittest.TestCase):
    def test_sums(self):
        self.assertEqual(answer("(187.40 * 1.15) / 4"), "53.8775")
        self.assertEqual(answer("4,738 x 2.65"), "12,555.7")
        self.assertEqual(answer("2^10"), "1024")
        self.assertEqual(answer("0.1 + 0.2"), "0.3")
        self.assertEqual(answer("avg(4, 5, 6)"), "5")
        self.assertEqual(answer("what is 5+5?"), "10")

    def test_percentages_the_way_people_say_them(self):
        self.assertEqual(answer("18% of 340"), "61.2")
        self.assertEqual(answer("340 + 15%"), "391")
        self.assertEqual(answer("187.40 - 20%"), "149.92")

    def test_the_sum_is_echoed(self):
        self.assertEqual(calc._calculate("18% of 340"), "18% of 340 = 61.2")


class Refused(unittest.TestCase):
    def test_nothing_but_math_runs(self):
        for bad in ("__import__('os').system('ls')", "open('/etc/passwd')", "().__class__",
                    "[x for x in range(9)]", "lambda: 1", "round(1, ndigits=2)"):
            self.assertIn("Couldn't work out", calc._calculate(bad), bad)

    def test_huge_numbers_are_refused_not_computed(self):
        self.assertIn("too big", calc._calculate("9**9**9"))
        self.assertIn("whole number", calc._calculate("factorial(100000)"))

    def test_divide_by_zero_and_too_long(self):
        self.assertIn("divides by zero", calc._calculate("1/0"))
        self.assertIn("too long", calc._calculate("1+" * 150 + "1"))


@unittest.skipUnless(HAVE_PINT, "pint isn't installed")
class Units(unittest.TestCase):
    def test_conversions(self):
        self.assertEqual(calc._calculate("160 F to C"), "160 F = 71.111111 °C")
        self.assertEqual(answer("100 C to F"), "212 °F")
        self.assertEqual(answer("5 miles in km"), "8.04672 km")
        self.assertEqual(answer("60 mph to km/h"), "96.56064 km/h")
        self.assertEqual(answer("6 feet in cm"), "182.88 cm")

    def test_different_kinds_of_thing_are_refused(self):
        self.assertIn("density", calc._calculate("2 cups to grams"))
        self.assertIn("Couldn't read", calc._calculate("10 apples to oranges"))


if __name__ == "__main__":
    unittest.main()
