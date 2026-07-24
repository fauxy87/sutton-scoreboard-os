#!/usr/bin/env python3

def pad(value, length):
    value = str(value).strip()
    if value == "" or value == "-":
        value = "0"
    return value.rjust(length, "-")


def parse_score(state, incoming):
    score = incoming.split(" &", 1)[0]
    if "/" in score:
        total, wickets = score.split("/", 1)
        state.update("total", pad(total, 3))
        state.update("wickets", wickets.replace("10", "-"))


def parse_overs(state, incoming):
    overs = incoming.split(".", 1)[0]
    state.update("overs", pad(overs, 2))


def parse_batter1_name(state, incoming):
    state.update("bat_a_name", incoming)


def parse_batter2_name(state, incoming):
    state.update("bat_b_name", incoming)


def parse_batter1_score(state, incoming):
    state.update("bat_a_runs", pad(incoming, 3))


def parse_batter2_score(state, incoming):
    state.update("bat_b_runs", pad(incoming, 3))


def parse_batter1_balls(state, incoming):
    state.update("bat_a_balls", incoming)


def parse_batter2_balls(state, incoming):
    state.update("bat_b_balls", incoming)


def parse_batter1_striker(state, incoming):
    state.update("bat_a_striker", incoming)


def parse_batter2_striker(state, incoming):
    state.update("bat_b_striker", incoming)


def parse_batting_team(state, incoming):
    state.update("batting_team", incoming)


def parse_fielding_team(state, incoming):
    state.update("fielding_team", incoming)


def parse_bowler1_name(state, incoming):
    state.update("bowler_a_name", incoming)


def parse_bowler1_figures(state, incoming):
    state.update("bowler_a_figures", incoming)


def parse_bowler2_name(state, incoming):
    state.update("bowler_b_name", incoming)


def parse_bowler2_figures(state, incoming):
    state.update("bowler_b_figures", incoming)


def parse_current_over(state, incoming):
    state.update("current_over", incoming)


def parse_last_wicket(state, incoming):
    state.update("last_wicket", incoming)


def parse_partnership(state, incoming):
    # Some packets may contain "16" or "16/6"
    value = incoming.split("/", 1)[0]
    state.update("partnership", value)


def ignore_packet(state, incoming):
    return


PACKET_HANDLERS = {
    "BTS": parse_score,
    "OVB": parse_overs,

    "B1N": parse_batter1_name,
    "B1S": parse_batter1_score,
    "B1B": parse_batter1_balls,
    "B1K": parse_batter1_striker,
    "B1D": ignore_packet,

    "B2N": parse_batter2_name,
    "B2S": parse_batter2_score,
    "B2B": parse_batter2_balls,
    "B2K": parse_batter2_striker,
    "B2D": ignore_packet,

    "BTN": parse_batting_team,
    "FTN": parse_fielding_team,

    "COV": parse_current_over,
    "LWK": parse_last_wicket,
    "PSH": parse_partnership,

    "BTR": ignore_packet,
    "BTW": ignore_packet,
    "F1N": parse_bowler1_name,
    "F1S": parse_bowler1_figures,
    "F2N": parse_bowler2_name,
    "F2S": parse_bowler2_figures,
    "RRQ": ignore_packet,
    "RRR": ignore_packet,
    "OVR": ignore_packet,
}


def parse_playcricket_packet(state, packet):
    packet = packet.strip()

    if len(packet) < 3:
        return state

    score_type = packet[0:3]
    incoming = packet[3:].strip()

    handler = PACKET_HANDLERS.get(score_type)

    if handler:
        handler(state, incoming)
    else:
        print("UNKNOWN PACKET:", score_type, incoming)

    return state
