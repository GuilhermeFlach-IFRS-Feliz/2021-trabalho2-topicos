# Reach Bot

![Reach Bot Logo](https://pbs.twimg.com/profile_images/1419033375545962500/SNEo4W8F_bigger.jpg "Reach Bot Logo")

Bot de Twitter que te ajuda a entender o seu alcance.

## Setup

1. Setar as variáveis de ambiente com as credencias do Twitter:

- TWAUTH_APP_CONSUMER_KEY
- TWAUTH_APP_CONSUMER_SECRET
- TWAUTH_APP_TOKEN_BOT
- TWAUTH_APP_SECRET_BOT

2. Instalar dependências (requer pipenv - instalar com pip install pipenv):
   1. `pipenv install`
   2. `pipenv shell`
3. Rodar:
   1. `python3 ./main.py`;

O callback URL do app deve ser /callback, caso contrário mudar no códido
