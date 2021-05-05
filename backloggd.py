import requests, csv, json, sys, time
from datetime import datetime

s = requests.Session()

# get IGDB creds
with open('backloggd.json','r') as f:
    j = json.loads(f.read())

id = j['id']
secret = j['secret']
backloggd_id = j['backloggd_id']
backloggd_csrf = j['csrf']
backloggd_cookie = j['cookie']

access_url = 'https://id.twitch.tv/oauth2/token?client_id=%s&client_secret=%s&grant_type=client_credentials' % (id, secret)
r = s.post(access_url)
response = json.loads(r.text)

access_token = response['access_token']
expires = int(response['expires_in'])
endpoint = 'https://api.igdb.com/v4/games/'
headers = {'Client-ID': id, 'Authorization': 'Bearer ' + access_token}

BACKLOGGD_HEADERS = {
  'Connection': 'keep-alive',
  'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="90", "Google Chrome";v="90"',
  'Accept': '*/*',
  'X-CSRF-Token': '',
  'X-Requested-With': 'XMLHttpRequest',
  'sec-ch-ua-mobile': '?0',
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36',
  'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
  'Origin': 'https://www.backloggd.com',
  'Sec-Fetch-Site': 'same-origin',
  'Sec-Fetch-Mode': 'cors',
  'Sec-Fetch-Dest': 'empty',
  'Referer': 'https://www.backloggd.com/',
  'Accept-Language': 'en-US,en;q=0.9',
  'Cookie': '',
}

def get_yearbounding_timestamps(year):
    early = datetime(year, 1, 1)
    late = datetime(year + 1, 1, 1)
    return int(early.timestamp()), int(late.timestamp())

def update_cookie(august):
    BACKLOGGD_HEADERS['Cookie'] = 'cookies_consent=true;remember_user_token=1; _august_app_session=' + august

def update_csrf(key):
    BACKLOGGD_HEADERS['X-CSRF-Token'] = key

def get_game_id(name, early, late):
    try:
        body = 'fields name; search "%s"; where release_dates.date >= %s & release_dates.date <= %s;' % (name, early, late)
        r = s.post(endpoint, headers=headers, data=body)
        j = json.loads(r.text)
        actual_game = [g['id'] for g in j]
        if len(actual_game) > 0:
            return actual_game[0] # this is the ID
        else:
            return None # game not found
    except:
        print("Error getting game id " + name)
        return None

def add_game(game_id, rating):
    data = {
        'play_toggle': True,
        'playing_toggle': False,
        'backlog_toggle': False,
        'wishlist_toggle': False,
        'rating_modal': rating,
        'status': 'completed',
        'review': '',
        'review_platform': '',
        'hours': '',
        'minutes': '',
        'log_id': ''
    }
    backloggd_url = 'https://www.backloggd.com/api/user/' + str(backloggd_id) + '/log/' + str(game_id)
    add_request = s.post(backloggd_url, headers=BACKLOGGD_HEADERS, params=data)
    return add_request.status_code


# Match game names to IGDB IDs, submit to backloggd
# Games with no IDs will be written to text file notfound.txt
update_cookie(backloggd_cookie)
update_csrf(backloggd_csrf)
not_found_games = open('notfound.txt','w')
start_from_row = 107
index = 0
with open('games.csv','r') as csvfile:
    reader = csv.reader(csvfile, delimiter=',')
    for row in reader:
        if index < start_from_row:
            index += 1
            continue
        name = row[0]
        rating = int(row[5])* 2
        early, late = get_yearbounding_timestamps(int(row[2]))
        trying = True
        while trying:
            game_id = get_game_id(name, early, late)
            if game_id is not None:
                status = add_game(game_id, rating)
                trying = False
                if status < 400:
                    print('Added ' + name)
                elif status == 429:
                    print('Hit request limit, pausing')
                    trying = True # try again
                    time.sleep(60*3)
                    print('Trying again')
                else:
                    print('Game already added or headers error ' + name)
            else:
                not_found_games.write(name + '\n')
                trying = False
not_found_games.close()
