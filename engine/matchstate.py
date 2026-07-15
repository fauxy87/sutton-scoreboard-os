#!/usr/bin/env python3

import time

class MatchState:
    def __init__(self):
        self.total = "--0"
        self.wickets = "0"
        self.overs = "-0"
        self.target = "---"

        self.bat_a_name = "-"
        self.bat_a_runs = "--0"
        self.bat_a_balls = "-"

        self.bat_b_name = "-"
        self.bat_b_runs = "--0"
        self.bat_b_balls = "-"

        self.batting_team = "-"
        self.fielding_team = "-"

        self.current_over = "-"
        self.partnership = "0"
        self.last_wicket = "---"
        self.last_man = "---"
        self.runs_required = "---"

        self.last_packet_time = time.time()
        self.changed = False

    def update(self, field, value):
        if hasattr(self, field):
            if getattr(self, field) != value:
                setattr(self, field, value)
                self.changed = True
                self.last_packet_time = time.time()

    def snapshot(self):
        return {
            "total": self.total,
            "wickets": self.wickets,
            "overs": self.overs,
            "target": self.target,
            "Bat1Name": self.bat_a_name,
            "BatAscore": self.bat_a_runs,
            "BatABallsFaced": self.bat_a_balls,
            "Bat2Name": self.bat_b_name,
            "BatBscore": self.bat_b_runs,
            "BatBBallsFaced": self.bat_b_balls,
            "BatTeamName": self.batting_team,
            "FieldTeamName": self.fielding_team,
            "CurrentOver": self.current_over,
            "PshipTOT": self.partnership,
            "LastWicket": self.last_wicket,
            "LastMan": self.last_man,
            "RunsRequired": self.runs_required,
        }
