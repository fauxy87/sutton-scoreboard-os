import unittest

from engine import event_engine
from engine.matchstate import MatchState
from engine.parser import parse_playcricket_packet


class ParserTests(unittest.TestCase):
    def test_play_cricket_score_and_match_fields(self):
        state = MatchState()

        packets = (
            "BTS123/4 & 0",
            "OVB17.3",
            "B1NCraig Faux",
            "B1S42",
            "B1B31",
            "BTN Sutton CC",
            "FTN Ely CC",
            "BTT150",
            "RRQ27",
        )

        for packet in packets:
            parse_playcricket_packet(state, packet)

        self.assertEqual(state.total, "123")
        self.assertEqual(state.wickets, "4")
        self.assertEqual(state.overs, "17")
        self.assertEqual(state.bat_a_name, "Craig Faux")
        self.assertEqual(state.bat_a_runs, "-42")
        self.assertEqual(state.bat_a_balls, "31")
        self.assertEqual(state.batting_team, "Sutton CC")
        self.assertEqual(state.fielding_team, "Ely CC")
        self.assertEqual(state.target, "150")
        self.assertEqual(state.runs_required, "-27")

    def test_all_out_is_shown_as_dash(self):
        state = MatchState()
        parse_playcricket_packet(state, "BTS188/10")

        self.assertEqual(state.total, "188")
        self.assertEqual(state.wickets, "-")


class EventTests(unittest.TestCase):
    @staticmethod
    def snapshot(total, wickets, batter_runs):
        return {
            "total": str(total),
            "wickets": str(wickets),
            "overs": "12",
            "Bat1Name": "Batter One",
            "BatAscore": str(batter_runs),
            "Bat2Name": "Batter Two",
            "BatBscore": "0",
            "BatTeamName": "Sutton CC",
            "FieldTeamName": "Visitors",
            "CurrentOver": "1 2",
            "LastWicket": "100",
        }

    def test_four_and_fifty_are_both_detected(self):
        previous = self.snapshot(96, 2, 46)
        current = self.snapshot(100, 2, 50)

        event_types = {
            event["type"]
            for event in event_engine.detect_events(previous, current)
        }

        self.assertEqual(event_types, {"FOUR", "FIFTY"})

    def test_six_is_detected(self):
        previous = self.snapshot(100, 2, 24)
        current = self.snapshot(106, 2, 30)

        events = event_engine.detect_events(previous, current)

        self.assertEqual([event["type"] for event in events], ["SIX"])

    def test_wicket_suppresses_boundary_event(self):
        previous = self.snapshot(100, 2, 24)
        current = self.snapshot(104, 3, 28)

        events = event_engine.detect_events(previous, current)

        self.assertEqual([event["type"] for event in events], ["WICKET"])


if __name__ == "__main__":
    unittest.main()
