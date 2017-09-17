#!/usr/bin/env python3

import os, re
from collections import OrderedDict, Counter
from yattag import Doc, indent


PRODUCERS = {}
with open('cards.txt', 'r') as card_file:
    for line in card_file:
        if line.startswith('N:'):
            card_name = ' '.join(line.split(':')[1:]).strip()
        elif line.startswith('G:'):
            PRODUCERS[card_name] = line.split(':')[1].lower().strip()

PHASES = (
        'Explore',
        'Develop',
        'Settle',
        'Consume',
        'Produce'
        )

VARIANTS = {
        'Explore +1,+1': 'Explore',
        'Explore +5': 'Explore',
        'Consume-Trade': 'Consume',
        'Consume-x2': 'Consume',
        }


def get_color(player):
    colors = ('red', 'green', 'yellow', 'cyan')
    color = player.lower() if player.lower() in colors else 'blue'
    return color


logs = [f for f in os.listdir('/tmp') if f.startswith('export_')]
log = max(logs)
print('Processing {} ...'.format(log))


messages = []
with open('/tmp/' + log, 'r') as log_file:
    # Note to future self:
    # (:?)? is an optional non-capturing group
    # which may contain a normal group.
    pattern = r'.*<Message(?: format="(\w+)")?>([^<]*)</Message>\n'
    for line in log_file:
        match = re.search(pattern, line)
        if match:
            fmt, message = match.groups()
            messages.append((message, fmt))


def get_phase_name(choice):
    return choice if choice not in VARIANTS else VARIANTS[choice]


def updated_choices(choices, msg):
    # TODO: 2 Player Advanced needs 2 choices per player.
    if ' chooses ' in msg:
        player_name, choice = re.search(r'(.+) chooses (.+)\.', msg).groups()
        phase_name = get_phase_name(choice)
        choices[player_name] = choice
    return choices


class Phase:
    ''' Stores information about game state at the start of the phase
    and about gains players made during the phase. '''
    def __init__(self, msg, choices, players):
        self.name = re.search(r'--- (\w+) phase ---', msg).group(1)
        self.bonuses = []
        self.players = []
        for player_name in players:
            player = {
                    'name': player_name,
                    'placed': [],
                    'numbers': Counter(),
                    }
            self.players.append(player)
        for player_name, choice in choices.items():
            if get_phase_name(choice) == self.name:
                self.bonuses.append((player_name, choice))

    def update(self, msg, fmt, phase):
        ''' Update phase based on log message '''
        player = counter = None
        # Not checking 'split()[0] in line' because name might be
        # multi-word.
        for pl in self.players:
            if msg.startswith(pl['name']):
                player = pl
                counter = player['numbers']
                break
        if not player:
            return

        # exploration:
        if 'and keeps' in msg:
            pattern = r'.+ draws (\d+) and keeps (\d+).'
            explored, kept = re.search(pattern, msg).groups()
            counter['explored'] += int(explored)
            counter['kept'] += int(kept)

        # placement of cards:
        if 'places' in msg:
            placed = re.search(r'.+ places ([^.]+).', msg).group(1)
            player['placed'].append(placed)

        # cards and VPs gained:
        if 'receives' in msg:
            cards = points = 0
            if 'Explore' in msg:
                return
            # Sentient Robots, Scientific Cruisers are handled in
            # Produce and Consume summary lines.
            if 'from' in msg and self.name not in ('Settle', 'Develop'):
                return
            elif self.name in ('Develop', 'Settle'):
                cards = re.search(r'receives (\d+) cards? from', msg).group(1)
            elif 'VP' not in msg:
                pattern = r'receives (\d+) cards? for (Produce|Consume) phase'
                cards = re.search(pattern, msg).group(1)
            elif 'card' not in msg:
                pattern = r'.+ receives (\d+) VPs? for Consume phase.'
                points = re.search(pattern, msg).group(1)
            elif 'card' in msg and 'VP' in msg:
                pattern = r'.+ receives (\d+) cards? and (\d+) VPs?'
                cards, points = re.search(pattern, msg).groups()
            counter['cards'] += int(cards)
            counter['points'] += int(points)

        # production of goods:
        if 'produces on' in msg:
            planet = re.search(r'.+ produces on (.+)\.', msg).group(1)
            counter[PRODUCERS[planet]] += 1


def render_actions(phase):
    # TODO: Order changes between runs. Do something
    # about the OrderedDict
    for player, choice in phase.bonuses:
        line('li', choice, klass=get_color(player))


def render_gains(player):
    content = ''
    pl = player
    counter = player['numbers']

    explored = ''
    if  counter['explored']:
        explored = '+%s(%s)' % (counter['kept'], counter['explored'])

    placed = ', '.join(pl['placed'])

    cards = counter['cards']
    cards = '' if not cards else '+%scards' % cards
    points = counter['points']
    points = '' if not points else '+%spoints' % points

    content += ' '.join([explored, placed, cards, points])
    text(content)

    # TODO: kinds of goods sometimes have gaps between
    # them for no apparent reason.
    for kind in ('novelty', 'rare', 'gene', 'alien'):
        # Don't add empty spans to DOM tree
        if counter[kind]:
            with tag('span', klass=kind):
                text('#' * counter[kind])


players = OrderedDict()
msg, fmt = messages[0]
while 'Round' not in msg:
    if ' starts with ' in msg:
        player, homeworld = re.search(r'(.+) starts with (.*)\.', msg).groups()
        players[player] = homeworld
    msg, fmt = messages.pop(0)


rounds = []
while 'End of game' not in msg:
    choices = {}
    rnd = []
    while 'phase ---' not in msg:
        # Between Round and Phase
        choices = updated_choices(choices, msg)
        msg, fmt = messages.pop(0)
    while '===' not in msg:
        if 'phase ---' in msg:
            rnd.append(Phase(msg, choices, players))
        else:
            rnd[-1].update(msg, fmt, rnd[-1])
        msg, fmt = messages.pop(0)
    rounds.append(rnd)


doc, tag, text, line= Doc().ttl()
with tag('html'):
    with tag('meta'):
        doc.stag('link', rel="stylesheet", href="style.css")
    with tag('body'):
        for round_number, rnd in enumerate(rounds, 1):
            line('h2', 'Round %s' % round_number)
            with tag('table'):
                for phase in rnd:
                    with tag('tr'):
                        with tag('td', klass='action'):
                            render_actions(phase)
                        for player in phase.players:
                            with tag('td'):
                                render_gains(player)


output = open('report.html', 'w')
print("Generating 'report.html' ...")
print(indent(doc.getvalue()), file=output)

