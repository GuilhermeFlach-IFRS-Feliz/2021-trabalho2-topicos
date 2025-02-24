import os
from flask import Flask, render_template, request, url_for
import oauth2 as oauth
import urllib.request
import urllib.parse
import urllib.error
import json
import mysql.connector
import time
import threading
from datetime import datetime, timedelta
from TwitterAPI import TwitterAPI
from pprint import pprint
import schedule
import ast



from dotenv import load_dotenv

load_dotenv()


mydb = mysql.connector.connect(
  host="localhost",
  user="root",
  password="",
  database="topicos"
)

app = Flask(__name__)

app.debug = False

request_token_url = 'https://api.twitter.com/oauth/request_token'
access_token_url = 'https://api.twitter.com/oauth/access_token'
authorize_url = 'https://api.twitter.com/oauth/authorize'
show_user_url = 'https://api.twitter.com/1.1/users/show.json'

# Support keys from environment vars (Heroku).
app.config['APP_CONSUMER_KEY'] = os.getenv(
    'TWAUTH_APP_CONSUMER_KEY', 'API_Key_from_Twitter')
app.config['APP_CONSUMER_SECRET'] = os.getenv(
    'TWAUTH_APP_CONSUMER_SECRET', 'API_Secret_from_Twitter')

app.config['ACCESS_TOKEN_BOT'] = os.getenv(
    'TWAUTH_APP_TOKEN_BOT', 'API_Key_from_Twitter')
app.config['ACCESS_SECRET_BOT'] = os.getenv(
    'TWAUTH_APP_SECRET_BOT', 'API_Key_from_Twitter')

print(app.config['ACCESS_TOKEN_BOT'], app.config['ACCESS_SECRET_BOT'])

# alternatively, add your key and secret to config.cfg
# config.cfg should look like:
# APP_CONSUMER_KEY = 'API_Key_from_Twitter'
# APP_CONSUMER_SECRET = 'API_Secret_from_Twitter'
app.config.from_pyfile('config.cfg', silent=True)

oauth_store = {}


@app.route('/')
def hello():
    return render_template('index.html')


@app.route('/start')
def start():
    # note that the external callback URL must be added to the whitelist on
    # the developer.twitter.com portal, inside the app settings
    app_callback_url = url_for('callback', _external=True)

    # Generate the OAuth request tokens, then display them
    consumer = oauth.Consumer(
        app.config['APP_CONSUMER_KEY'], app.config['APP_CONSUMER_SECRET'])
    client = oauth.Client(consumer)
    resp, content = client.request(request_token_url, "POST", body=urllib.parse.urlencode({
                                   "oauth_callback": app_callback_url}))

    if resp['status'] != '200':
        error_message = 'Invalid response, status {status}, {message}'.format(
            status=resp['status'], message=content.decode('utf-8'))
        return render_template('error.html', error_message=error_message)

    request_token = dict(urllib.parse.parse_qsl(content))
    oauth_token = request_token[b'oauth_token'].decode('utf-8')
    oauth_token_secret = request_token[b'oauth_token_secret'].decode('utf-8')

    oauth_store[oauth_token] = oauth_token_secret
    return render_template('start.html', authorize_url=authorize_url, oauth_token=oauth_token, request_token_url=request_token_url)


@app.route('/callback')
def callback():
    # Accept the callback params, get the token and call the API to
    # display the logged-in user's name and handle
    oauth_token = request.args.get('oauth_token')
    oauth_verifier = request.args.get('oauth_verifier')
    oauth_denied = request.args.get('denied')

    # if the OAuth request was denied, delete our local token
    # and show an error message
    if oauth_denied:
        if oauth_denied in oauth_store:
            del oauth_store[oauth_denied]
        return render_template('error.html', error_message="the OAuth request was denied by this user")

    if not oauth_token or not oauth_verifier:
        return render_template('error.html', error_message="callback param(s) missing")

    # unless oauth_token is still stored locally, return error
    if oauth_token not in oauth_store:
        return render_template('error.html', error_message="oauth_token not found locally")

    oauth_token_secret = oauth_store[oauth_token]

    # if we got this far, we have both callback params and we have
    # found this token locally

    consumer = oauth.Consumer(
        app.config['APP_CONSUMER_KEY'], app.config['APP_CONSUMER_SECRET'])
    token = oauth.Token(oauth_token, oauth_token_secret)
    token.set_verifier(oauth_verifier)
    client = oauth.Client(consumer, token)

    resp, content = client.request(access_token_url, "POST")
    access_token = dict(urllib.parse.parse_qsl(content))

    screen_name = access_token[b'screen_name'].decode('utf-8')
    user_id = access_token[b'user_id'].decode('utf-8')

    # These are the tokens you would store long term, someplace safe
    real_oauth_token = access_token[b'oauth_token'].decode('utf-8')
    real_oauth_token_secret = access_token[b'oauth_token_secret'].decode(
        'utf-8')

    cursor = mydb.cursor()

    cursor.execute("INSERT IGNORE INTO usuarios (id, oauth_token, oauth_token_secret) VALUES (%s, %s, %s)", (user_id, real_oauth_token, real_oauth_token_secret))

    mydb.commit()

    # Call api.twitter.com/1.1/users/show.json?user_id={user_id}
    real_token = oauth.Token(real_oauth_token, real_oauth_token_secret)
    real_client = oauth.Client(consumer, real_token)
    real_resp, real_content = real_client.request(
        show_user_url + '?user_id=' + user_id, "GET")

    if real_resp['status'] != '200':
        error_message = "Invalid response from Twitter API GET users/show: {status}".format(
            status=real_resp['status'])
        return render_template('error.html', error_message=error_message)

    response = json.loads(real_content.decode('utf-8'))

    friends_count = response['friends_count']
    statuses_count = response['statuses_count']
    followers_count = response['followers_count']
    name = response['name']

    # don't keep this token and secret in memory any longer
    del oauth_store[oauth_token]

    return render_template('callback-success.html', screen_name=screen_name, user_id=user_id, name=name,
                           friends_count=friends_count, statuses_count=statuses_count, followers_count=followers_count, access_token_url=access_token_url)


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error_message='uncaught exception'), 500

def job():
        cursor = mydb.cursor()

        cursor.execute("SELECT * FROM usuarios")
        usuarios = cursor.fetchall()
       
        # Iterar pelos usuários do banco e requisitar as informações deles 
        for usuario in usuarios:
            uid = usuario[0]
            oath_token = usuario[1]
            oath_secret = usuario[2]

            api = TwitterAPI(app.config['APP_CONSUMER_KEY'], app.config['APP_CONSUMER_SECRET'], oath_token, oath_secret, api_version="2")

            date = str(datetime.date(datetime.now()) - timedelta(days=7))
            date += "T00:00:00Z"

            # Fazer a requisição e armazenar a resposta
            params = {'expansions':'author_id', 'tweet.fields': 'organic_metrics', 'start_time': date, 'user.fields' : 'name'}
            tweets = api.request(f'users/:{uid}/tweets', params)

            # Verificar se o usuário revogou acesso
            if (tweets.status_code == 401):
                # Remover usuário da tabela
                cursor = mydb.cursor()
                cursor.execute("DELETE FROM usuarios WHERE id=%s", (uid,))
                mydb.commit()
                continue

            # Converter as informações de bytes para dicionarios
            content = tweets.response.content
            dict_str = content.decode("UTF-8")
            responseData_dict = ast.literal_eval(dict_str)
            
            # Verificar se houveram tweets no período de tempo
            if "data" not in responseData_dict:
                continue

            tweet_list = responseData_dict['data']
            user_info = responseData_dict['includes']['users'][0]

            # Pegar informacoes do usuário
            user_name = user_info['name']
            user_at = user_info['username']


            # Pegar informações dos tweets
            tweet_total = 0
            impression_total = 0
            retweet_total = 0
            like_total = 0
            reply_total = 0
            user_profile_clicks_total = 0

            # Iterar pelos tweets e fazer a soma das informações        
            for tweet in tweet_list:
                tweet_total += 1

                tweet_info = tweet['organic_metrics']
                impression_total += tweet_info['impression_count']
                retweet_total += tweet_info['retweet_count']
                like_total += tweet_info['like_count']
                reply_total += tweet_info['reply_count']
                user_profile_clicks_total += tweet_info['user_profile_clicks']

            # Calcular as Médias
            impression_avg = impression_total / tweet_total
            retweet_avg = retweet_total / tweet_total
            like_avg = like_total / tweet_total 
            reply_avg = reply_total / tweet_total 
            user_profile_clicks_avg = user_profile_clicks_total / tweet_total 

            # Construir a mensagem
            text = f"Olá {user_name} (@{user_at}). Nessa última semana os seus {tweet_total} tweets tiveram uma média de {impression_avg} visualizações, {like_avg} likes e {retweet_avg} retweets! Adicionalmente, as pessoas responderam, em média, {reply_avg} vezes aos seus tweets e clickaram no seu perfil {user_profile_clicks_avg} vezes (a partir de seus tweets)."

            api = TwitterAPI(app.config['APP_CONSUMER_KEY'], app.config['APP_CONSUMER_SECRET'], app.config['ACCESS_TOKEN_BOT'], app.config['ACCESS_SECRET_BOT'])

            event = {
	        "event": {
		        "type": "message_create",
		        "message_create": {
			        "target": {
				        "recipient_id": uid
			        },
			        "message_data": {
				        "text": text
			            }
		            }
	            }
            }
            response = api.request("direct_messages/events/new", json.dumps(event))
            print(response.text)


def sched():
    schedule.every().saturday.at("12:00").do(job)

    while True:
        schedule.run_pending()
        time.sleep(30)

t1 = threading.Thread(target=app.run)
t2 = threading.Thread(target=sched)
if __name__ == '__main__':
    t1.start()
    t2.start()
    
    




