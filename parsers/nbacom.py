import json
import logging
from math import modf
import pprint
import re


class NBAComParser:
    '''
    Parses json endpoints of stats.nba.com into lists of dictionaries

    Usage:
        s = NBAComScraper()
        jsondoc = s.player_stats()
        p = NBAComParser()
        stats = p.player_stats(jsondoc)

        content = s.teams()
        teams = p.teams(content)

    '''

    def __init__(self):

        logging.getLogger(__name__).addHandler(logging.NullHandler())

    def _fix_linescores(self, linescores):
        '''
        Preprocessing for insertion into database
        '''
        fixed_linescores = []
        exclude = ['game_sequence']

        for linescore in linescores:
            fixed_linescore = {k.lower():v for k,v in linescore.items()}
            fixed_linescore.pop('game_sequence', None)

            fixed_linescore['team_game_id'] = '{0}:{1}'.format(fixed_linescore['team_id'], fixed_linescore['game_id'])
            twl = fixed_linescore.get('team_wins_losses', None)

            if twl:
                wins, losses = twl.split('-')

                if wins and losses:
                    fixed_linescore['team_wins'] = wins
                    fixed_linescore['team_losses'] = losses

            fixed_linescores.append(fixed_linescore)

        return fixed_linescores

    def _fix_player_inof(self, player_info):
        return player_info

    def boxscore(self, content, game_date=None):
        '''
        Represents single nba.com boxscore

        Arguments:
            content(dict): parsed json
            game_date(str): string representing date of game for boxscore

        Returns:
            players(list): dictionary of stats for each player
            teams(list): dictionary of stats for each team
            starter_bench(list): dictionary of stats broken down by starter/bench
        '''

        players = []
        teams = []
        starter_bench = []

        for rs in content['resultSets']:
            if rs.get('name') == 'PlayerStats':
                player_results = rs
            elif rs.get('name') == 'TeamStats':
                team_results = rs
            elif rs.get('name') == 'TeamStarterBenchStats':
                starter_bench_results = rs

        # add game_date for convenience
        # standardize on TOV rather than TO; playerstats uses TOV
        for row_set in player_results.get('rowSet'):
            player = dict(zip(player_results.get('headers'), row_set))

            if game_date:
                player['GAME_DATE'] = game_date

            if 'MIN' in player:
                player['MIN_PLAYED'], player['SEC_PLAYED'] = player['MIN'].split(':')

            if 'TOV' in player:
                player['TOV'] = player.pop('TO')

            players.append(player)

        # add game_date for convenience
        for result in team_results['rowSet']:
            team = dict(zip(team_results['headers'], result))

            if game_date:
                team['GAME_DATE'] = game_date

            teams.append(team)

        # starter_bench
        for result in starter_bench_results['rowSet']:
            sb = dict(zip(team_results['headers'], result))

            if game_date:
                sb['GAME_DATE'] = game_date

            starter_bench.append(sb)

        return players, teams, starter_bench

    def one_player_gamelogs(self, content):
        '''
        Parses gamelogs for one player

        Arguments:
            content(dict): parsed JSON

        Returns:
            player_gl(list): list of gamelog dictionaries
        '''

        player_gl =[]
        result_set = content['resultSets'][0]

        for row_set in result_set['rowSet']:
            game_log = dict(zip(result_set['headers'], row_set))
            player_gl.append(game_log)

        return player_gl

    def one_team_gamelogs(self,content):
        '''
        Parses gamelogs for one team

        Arguments:
            content(dict): parsed JSON

        Returns:
            team_gl(list): list of gamelog dictionaries

        '''

        team_gl =[]
        result_set = content['resultSets'][0]

        for row_set in result_set['rowSet']:
            game_log = dict(zip(result_set['headers'], row_set))
            team_gl.append(game_log)

        return team_gl

    def player_info(self,content):
        '''
        Dictionary about individual player, includes name, id, etc.

        Arguments:
            content(dict): json parsed into dictionary

        Returns:
            dictionary about individual player, includes name, id, etc.
        '''
        result_set = content['resultSets'][0]
        headers = result_set.get('headers')
        rowset = result_set.get('rowSet')

        if headers and rowset:
            return dict(zip(headers,rowset[0]))

        else:
            raise ValueError('player_info failed: no headers or rowset')

    def players (self,content):

        p = []

        result_set = content['resultSets'][0]

        for row_set in result_set['rowSet']:
            p.append(dict(zip(result_set['headers'], row_set)))

        return p

    def playerstats(self,content,stat_date=None):
        '''
        Document has one line of stats per player

        Arguments:
            content(dict): parsed json from nba.com
            stat_date(str): in YYYY-YY format (2015-16)

        Returns:
            ps(list): list of dictionaries, each one is a player's stats

        '''

        ps = []

        result_set = content['resultSets'][0]

        for row_set in result_set['rowSet']:
            p = dict(zip(result_set['headers'], row_set))

            if stat_date:
                p['STATDATE'] = stat_date

            if 'MIN' in p:
                p['SEC_PLAYED'], p['MIN_PLAYED'] = modf(p['MIN'])

            ps.append(p)

        return ps

    def scoreboard(self,content,game_date=None):
        '''
        Arguments:
            content(str): json string    
            game_date(str): date string of the day of scoreboard

        Returns:
            sb(dict): {'date': game_date, 'game_headers': game_headers.values(), 'game_linescores': game_linescores, 'standings': standings}
        '''
        game_headers = {}
        game_linescores = []
        standings = []

        # want to get game_headers, east_standings, and west_standings
        # resultSets[0] is a list of games, with game_id, gamecode, teams, etc.
        for row_set in content['resultSets'][0]['rowSet']:
            game_header = dict(zip(content['resultSets'][0]['headers'], row_set))
            gamecode = game_header.get('GAMECODE', None)

            if gamecode:
                game_headers[gamecode] = game_header
            else:
                logging.error('no gamecode')

        # resultSets[1] are the game_linescores (includes results on a team-by-team, game-by-game basis)
        for row_set in content['resultSets'][1]['rowSet']:
            linescore_headers = [h.lower() for h in content['resultSets'][1]['headers']]
            linescore = dict(zip(linescore_headers, row_set))
            game_linescores.append(linescore)

        # resultSets[4] is a list of eastern_conference_standings
        for row_set in content['resultSets'][4]['rowSet']:
            standings.append(dict(zip(content['resultSets'][4]['headers'], row_set)))

        # resultSets[5] is a list of western_conference_standings
        for row_set in content['resultSets'][5]['rowSet']:
            standings.append(dict(zip(content['resultSets'][5]['headers'], row_set)))

        sb = {'date': game_date, 'game_headers': game_headers.values(), 'game_linescores': self._fix_linescores(game_linescores), 'standings': standings}
        return sb

    def season_gamelogs(self,content,player_or_team):

        gamelogs =[]

        if player_or_team == 'T':

            results = content['resultSets'][0]
            headers = results['headers']

            for result in results['rowSet']:
                gamelog = dict(zip(headers, result))

                # add opponent_score
                points = gamelog.get('PTS', None)
                plus_minus = gamelog.get('PLUS_MINUS', None)

                if points and plus_minus:
                    gamelog['OPPONENT_PTS'] = points - plus_minus

                gamelogs.append(gamelog)

        elif player_or_team == 'P':
            result_set = content['resultSets'][0]
            headers = result_set.get('headers')

            for row_set in result_set['rowSet']:
                player_game = dict(zip(headers,row_set))
                gamelogs.append(player_game)

        return gamelogs

    def team_dashboard(self, content):
        '''
        Dashboard has keys: parameters, overall, location, days_rest, wins_losses
        The value of each key is a list of dictionaries
        parameters: 1 item in list
        overall: 1 item in list
        location: 2 items - home and away
        days_rest: multiple items that vary - 0 days, 1 day, 2 days, 3 days, 4 days
        wins_losses: 2 items - wins and losses
        '''

        dashboard = {'parameters': [], 'overall': [], 'location': [], 'days_rest': [], 'wins_losses': []}

        dashboard['parameters'] = content['parameters']

        for result_set in content['resultSets']:
            logging.debug('result_set name: {0}'.format(result_set['name']))

            if result_set['name'] == 'OverallTeamDashboard':
                headers = result_set['headers']

                for row_set in result_set['rowSet']:
                    result = dict(zip(headers, row_set))
                    dashboard['overall'].append(result)

            elif result_set['name'] == 'LocationTeamDashboard':
                for row_set in result_set['rowSet']:
                    result = dict(zip(headers, row_set))
                    dashboard['location'].append(result)

            elif result_set['name'] == 'DaysRestTeamDashboard':
                for row_set in result_set['rowSet']:
                    result = dict(zip(headers, row_set))
                    dashboard['days_rest'].append(result)

            elif result_set['name'] == 'WinsLossesTeamDashboard':
                for row_set in result_set['rowSet']:
                    result = dict(zip(headers, row_set))
                    dashboard['wins_losses'].append(result)

        return dashboard

    def team_opponent_dashboard(self, content):
        '''
        Returns list of dictionaries, stats of opponents vs. each team
        '''

        teams = []

        result_set = content['resultSets'][0]
        headers = [h.lower() for h in result_set['headers']]

        for row_set in result_set['rowSet']:
            teams.append(dict(zip(headers, row_set)))

        return teams

    def teams(self, content):
        '''
        Returns list of string - "1610612737","ATL"
        TODO: parse this into dictionaries
        '''

        teams = {}
        pattern = re.compile(r'("(\d{10})","(\w{3})"),conf')

        return {match[2]: match[1] for match in re.findall(pattern, content)}

    def teamstats(self,content,stat_date=None):

        ts = []

        result_set = content['resultSets'][0]

        for row_set in result_set['rowSet']:
            t = dict(zip(result_set['headers'], row_set))

            if stat_date:
                t['STATDATE'] = stat_date

            ts.append(t)

        return ts

if __name__ == "__main__":
    pass